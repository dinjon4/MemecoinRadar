"""Ortak HTTP istemcisi: User-Agent başlığı, zaman aşımı ve otomatik tekrar deneme."""

import logging
import sqlite3
import time
from contextlib import closing

import requests

from radar import DATA_DIR, USER_AGENT

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 4
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Ücretsiz limitlere takılmamak için aynı adrese iki istek arasında en az bu kadar saniye beklenir.
# GeckoTerminal'in ücretsiz limiti pratikte belgelenenden sıkı (2026-10-08'de ~2,5 sn aralıkla 429 alındı).
MIN_INTERVAL_SECONDS = {
    "api.geckoterminal.com": 6.0,
    "api.dexscreener.com": 0.3,
    "api.rugcheck.xyz": 4.5,  # dakikada 15 istek (x-rate-limit-limit başlığı)
    "www.reddit.com": 10.0,   # RSS limiti sıkı (art arda isteklerde 429)
}

# Bu adreslerin sırası tarama servisi ile erken hacim servisi (iki ayrı süreç) arasında ortak tutulur;
# yoksa iki süreç birlikte ücretsiz limiti aşar. Sıra küçük bir SQLite dosyasında saklanır.
SHARED_HOSTS = {"api.geckoterminal.com", "api.dexscreener.com"}
SHARED_THROTTLE_PATH = DATA_DIR / "throttle.db"

_session = requests.Session()
# Bazı API'ler (ör. DexScreener) User-Agent olmayan isteklere 403 veriyor.
_session.headers["User-Agent"] = USER_AGENT
_last_request_at: dict[str, float] = {}


def _throttle(host: str) -> None:
    interval = MIN_INTERVAL_SECONDS.get(host, 0)
    if host in SHARED_HOSTS and interval:
        wait = reserve_shared_slot(host, interval)
        if wait is not None:
            if wait > 0:
                time.sleep(wait)
            return
    elapsed = time.monotonic() - _last_request_at.get(host, float("-inf"))
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request_at[host] = time.monotonic()


def reserve_shared_slot(host: str, interval: float, path=None) -> float | None:
    """Süreçler arası ortak sıradan bir istek hakkı ayırır; isteğe kadar beklenecek saniyeyi döner.

    Dosya kullanılamazsa None döner (o zaman süreç kendi içindeki bekleme ile devam eder).
    """
    path = path or SHARED_THROTTLE_PATH
    try:
        path.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30, isolation_level=None)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS slots (host TEXT PRIMARY KEY, next_at REAL NOT NULL)")
            conn.execute("BEGIN IMMEDIATE")  # aynı anda tek süreç okuyup yazsın
            row = conn.execute("SELECT next_at FROM slots WHERE host = ?", (host,)).fetchone()
            now = time.time()
            next_at = row[0] if row else now
            # Saat geri alındıysa veya kayıt bozuksa sonsuza kadar beklenmesin.
            if next_at > now + 10 * interval:
                next_at = now
            slot = max(now, next_at)
            conn.execute(
                "INSERT INTO slots (host, next_at) VALUES (?, ?) "
                "ON CONFLICT(host) DO UPDATE SET next_at = excluded.next_at",
                (host, slot + interval),
            )
            conn.execute("COMMIT")
        return slot - now
    except (sqlite3.Error, OSError) as e:
        log.debug("Ortak istek sırası kullanılamadı (%s), süreç içi bekleme kullanılıyor.", type(e).__name__)
        return None


def request(method: str, url: str, **kwargs) -> requests.Response:
    """İstek gönderir; limit aşımı, sunucu hatası ve bağlantı hatasında bekleyip tekrar dener.

    Son denemede de başarısız olursa hatayı fırlatır. 4xx hatalarında (429 hariç) tekrar denemez.
    """
    kwargs.setdefault("timeout", TIMEOUT_SECONDS)
    host = _short(url)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _throttle(host)
        try:
            resp = _session.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == MAX_ATTEMPTS:
                raise
            wait = 2 ** attempt
            log.warning("Bağlantı hatası (%s), %d sn sonra tekrar denenecek: %s", type(e).__name__, wait, _short(url))
            time.sleep(wait)
            continue

        if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
            wait = _retry_after(resp) or max(2 ** attempt, 2 * MIN_INTERVAL_SECONDS.get(host, 0))
            log.warning("HTTP %d, %d sn sonra tekrar denenecek: %s", resp.status_code, wait, _short(url))
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp
    raise AssertionError("buraya ulaşılmamalı")


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)


def _retry_after(resp: requests.Response) -> int | None:
    value = resp.headers.get("Retry-After")
    if value and value.isdigit():
        return min(int(value), 120)
    return None


def _short(url: str) -> str:
    """Loglarda sadece alan adını gösterir; yol ve sorgu gizli anahtar içerebilir (ör. Telegram bot token)."""
    return url.split("/")[2] if "://" in url else "?"
