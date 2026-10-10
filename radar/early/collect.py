"""Erken Hacim veri toplama: yeni ve hareketlenen havuzların dakikalık anlık görüntüleri.

Her turda:
1. GeckoTerminal'in "5 dk trend" (2 sayfa) ve "yeni havuzlar" listeleri okunur. Bu listeler havuzun
   son 5/15/60 dakikalık hacmini, alım/satım ve benzersiz alıcı/satıcı sayısını da içerir;
   bunlar 'gt' anlık görüntüsü olarak kaydedilir. Bonding curve havuzları da dahildir.
2. İzlenen havuzlar DexScreener'dan 30'arlı gruplar halinde güncellenir ('ds' anlık görüntüsü).
   İzlenen havuz: yeterince yeni, ve son 15 dk'da listelerde görülmüş ya da son 1 saatte işlem görmüş.
3. Saklama süresini geçen veriler silinir.

Kaynakların hazır verdiği 5 dk / 1 saat değerleri "şu an" bilgisidir; ivmeyi (hacim hızlanıyor mu)
görmek için bunları dakika dakika kendimiz kaydediyoruz.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from radar import http
from radar.sources import QUOTE_MINTS, geckoterminal

log = logging.getLogger(__name__)

DEXSCREENER_PAIRS_URL = "https://api.dexscreener.com/latest/dex/pairs/{chain}/{pairs}"
DS_BATCH_SIZE = 30
# Listede görülen havuz bu kadar süre, işlem gören havuz son işlemden sonra bu kadar süre ölçülür.
# (Yeni havuzların çoğu hiç işlem görmeden söner; onları uzun süre ölçmek veritabanını şişirir.)
FOLLOW_LISTED_MINUTES = 15
FOLLOW_ACTIVE_MINUTES = 60
WINDOWS = ("m5", "m15", "h1")
SNAPSHOT_COLUMNS = ["pool", "taken_at", "source", "price_usd", "market_cap_usd", "liquidity_usd"] + [
    f"{w}_{k}" for w in WINDOWS for k in ("volume", "buys", "sells", "buyers", "sellers")
]


@dataclass(frozen=True)
class Chain:
    name: str                    # veritabanındaki ad
    gt_network: str              # GeckoTerminal ağ kimliği
    ds_chain: str                # DexScreener zincir kimliği
    quote_tokens: frozenset      # memecoin olmayan karşı tokenlar (SOL, USDC…)


SOLANA = Chain("solana", "solana", "solana", frozenset(QUOTE_MINTS))
# BNB Chain Solana sonuçları görüldükten sonra eklenecek (karar: 2026-10-10).
CHAINS = [SOLANA]

# (yol, parametreler, açıklama)
GT_LISTS = [
    ("trending_pools", {"duration": "5m"}, "trend 5dk"),
    ("trending_pools", {"duration": "5m", "page": 2}, "trend 5dk s2"),
    ("new_pools", {}, "yeni"),
]


@dataclass
class Pool:
    pool: str
    chain: str
    token: str
    symbol: str
    dex: str
    created_at: datetime
    url: str


@dataclass
class RoundResult:
    listed: int      # listelerde görülen havuz
    new: int         # ilk kez görülen
    followed: int    # DexScreener'dan ölçülen
    snapshots: int   # kaydedilen anlık görüntü


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_gt_pool(item: dict, chain: Chain) -> tuple[Pool, dict] | None:
    """GeckoTerminal havuz kaydını (havuz, anlık görüntü) çiftine çevirir. Memecoin havuzu değilse None."""
    try:
        attrs = item["attributes"]
        rel = item["relationships"]
        base = rel["base_token"]["data"]["id"].split("_", 1)[1]
        quote = rel["quote_token"]["data"]["id"].split("_", 1)[1]
        created = datetime.fromisoformat(attrs["pool_created_at"].replace("Z", "+00:00"))
        dex = rel["dex"]["data"]["id"]
        address = attrs["address"]
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None
    # Memecoin genelde "base" taraftadır; değilse (ör. SOL/MEME) diğer taraf.
    token_is_base = base not in chain.quote_tokens
    token = base if token_is_base else quote
    if token in chain.quote_tokens:
        return None
    names = (attrs.get("name") or "").split(" / ")
    symbol = names[0 if token_is_base else 1].strip() if len(names) == 2 else ""

    snap = {
        "pool": address, "source": "gt",
        "price_usd": _float(attrs.get("base_token_price_usd" if token_is_base else "quote_token_price_usd")),
        "market_cap_usd": _float(attrs.get("market_cap_usd")) or _float(attrs.get("fdv_usd")),
        "liquidity_usd": _float(attrs.get("reserve_in_usd")),
    }
    txns, volume = attrs.get("transactions") or {}, attrs.get("volume_usd") or {}
    for w in WINDOWS:
        t = txns.get(w) or {}
        snap[f"{w}_volume"] = _float(volume.get(w))
        for k in ("buys", "sells", "buyers", "sellers"):
            snap[f"{w}_{k}"] = _int(t.get(k))
    pool = Pool(address, chain.name, token, symbol, dex, created,
                f"https://dexscreener.com/{chain.ds_chain}/{address}")
    return pool, snap


def parse_ds_pair(pair: dict) -> tuple[dict, dict] | None:
    """DexScreener havuz kaydını (token bilgisi, anlık görüntü) çiftine çevirir.

    DexScreener'da benzersiz alıcı sayısı ve 15 dk penceresi yok; o sütunlar boş kalır.
    """
    address = pair.get("pairAddress")
    if not address:
        return None
    snap = {
        "pool": address, "source": "ds",
        "price_usd": _float(pair.get("priceUsd")),
        "market_cap_usd": _float(pair.get("marketCap")) or _float(pair.get("fdv")),
        "liquidity_usd": _float((pair.get("liquidity") or {}).get("usd")),
    }
    txns, volume = pair.get("txns") or {}, pair.get("volume") or {}
    for w in WINDOWS:
        t = txns.get(w) or {}
        snap[f"{w}_volume"] = _float(volume.get(w))
        snap[f"{w}_buys"] = _int(t.get("buys"))
        snap[f"{w}_sells"] = _int(t.get("sells"))
        snap[f"{w}_buyers"] = snap[f"{w}_sellers"] = None
    base = pair.get("baseToken") or {}
    meta = {"name": base.get("name") or "", "symbol": base.get("symbol") or ""}
    return meta, snap


def is_active(snap: dict) -> bool:
    """Son 5 dakikada en az bir işlem var mı."""
    return ((snap.get("m5_buys") or 0) + (snap.get("m5_sells") or 0)) > 0


def save_pool(conn: sqlite3.Connection, pool: Pool, source: str, now_iso: str) -> bool:
    """Havuzu ekler veya 'listede görüldü' zamanını günceller. İlk kez görüldüyse True."""
    cur = conn.execute(
        "UPDATE ev_pools SET last_listed_at = ? WHERE pool = ?", (now_iso, pool.pool)
    )
    if cur.rowcount:
        return False
    conn.execute(
        """INSERT INTO ev_pools (pool, chain, token, name, symbol, dex, created_at, first_seen_at,
                                 last_listed_at, source, url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pool.pool, pool.chain, pool.token, pool.symbol, pool.symbol, pool.dex, _iso(pool.created_at),
         now_iso, now_iso, source, pool.url),
    )
    return True


def save_snapshot(conn: sqlite3.Connection, snap: dict, now_iso: str) -> None:
    row = {c: snap.get(c) for c in SNAPSHOT_COLUMNS}
    row["taken_at"] = now_iso
    conn.execute(
        f"INSERT OR REPLACE INTO ev_snapshots ({', '.join(SNAPSHOT_COLUMNS)}) "
        f"VALUES ({', '.join('?' * len(SNAPSHOT_COLUMNS))})",
        [row[c] for c in SNAPSHOT_COLUMNS],
    )
    if is_active(snap):
        conn.execute("UPDATE ev_pools SET last_active_at = ? WHERE pool = ?", (now_iso, snap["pool"]))


def pools_to_follow(conn: sqlite3.Connection, chain: Chain, max_age_hours: int, limit: int,
                    now: datetime) -> list[str]:
    """DexScreener'dan ölçülecek havuzlar: yeni, ve son 15 dk'da listelenmiş ya da son 1 saatte işlem görmüş.

    Sınır aşılırsa en son hareket gören havuzlar önce gelir.
    """
    listed_since = _iso(now - timedelta(minutes=FOLLOW_LISTED_MINUTES))
    active_since = _iso(now - timedelta(minutes=FOLLOW_ACTIVE_MINUTES))
    rows = conn.execute(
        """SELECT pool FROM ev_pools
           WHERE chain = ? AND created_at >= ? AND (last_listed_at >= ? OR last_active_at >= ?)
           ORDER BY MAX(last_listed_at, COALESCE(last_active_at, '')) DESC
           LIMIT ?""",
        (chain.name, _iso(now - timedelta(hours=max_age_hours)), listed_since, active_since, limit),
    )
    return [r["pool"] for r in rows]


def prune(conn: sqlite3.Connection, keep_days: int, now: datetime) -> int:
    """Saklama süresini geçen anlık görüntüleri ve havuzları siler. Silinen görüntü sayısını döner."""
    cutoff = _iso(now - timedelta(days=keep_days))
    deleted = conn.execute("DELETE FROM ev_snapshots WHERE taken_at < ?", (cutoff,)).rowcount
    conn.execute("DELETE FROM ev_pools WHERE created_at < ? AND last_listed_at < ?", (cutoff, cutoff))
    conn.commit()
    return deleted


def fetch_gt_list(chain: Chain, path: str, params: dict, label: str) -> list[dict]:
    url = f"{geckoterminal.BASE_URL}/networks/{chain.gt_network}/{path}"
    try:
        return http.get(url, params=params, headers=geckoterminal.HEADERS).json().get("data") or []
    except (requests.RequestException, ValueError, AttributeError) as e:
        log.warning("GeckoTerminal '%s' listesi okunamadı: %s", label, type(e).__name__)
        return []


def fetch_ds_pairs(chain: Chain, pools: list[str]) -> list[dict]:
    """Havuzları 30'arlı gruplar halinde DexScreener'dan okur. Okunamayan grup atlanır."""
    pairs = []
    for i in range(0, len(pools), DS_BATCH_SIZE):
        batch = pools[i:i + DS_BATCH_SIZE]
        try:
            data = http.get(DEXSCREENER_PAIRS_URL.format(chain=chain.ds_chain, pairs=",".join(batch))).json()
        except (requests.RequestException, ValueError) as e:
            log.warning("DexScreener'dan %d havuz alınamadı: %s", len(batch), type(e).__name__)
            continue
        pairs.extend((data or {}).get("pairs") or [])
    return pairs


def run_round(conn: sqlite3.Connection, cfg: dict, chain: Chain = SOLANA, now_fn=None) -> RoundResult:
    """Bir veri toplama turu (yukarıdaki 1–3. adımlar)."""
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    max_age = cfg["early_max_age_hours"]
    listed, new, snapshots = set(), 0, 0

    for path, params, label in GT_LISTS:
        items = fetch_gt_list(chain, path, params, label)
        now = now_fn()
        cutoff = now - timedelta(hours=max_age)
        for item in items:
            parsed = parse_gt_pool(item, chain)
            if not parsed:
                continue
            pool, snap = parsed
            if pool.created_at < cutoff or pool.pool in listed:
                continue
            listed.add(pool.pool)
            new += save_pool(conn, pool, label, _iso(now))
            save_snapshot(conn, snap, _iso(now))
            snapshots += 1
        conn.commit()

    follow = pools_to_follow(conn, chain, max_age, cfg["early_max_pools"], now_fn())
    wanted = set(follow)
    for pair in fetch_ds_pairs(chain, follow):
        parsed = parse_ds_pair(pair)
        if not parsed or parsed[1]["pool"] not in wanted:
            continue
        meta, snap = parsed
        save_snapshot(conn, snap, _iso(now_fn()))
        if meta["name"]:
            conn.execute("UPDATE ev_pools SET name = ?, symbol = COALESCE(?, symbol) WHERE pool = ?",
                         (meta["name"], meta["symbol"] or None, snap["pool"]))
        snapshots += 1
    conn.commit()

    prune(conn, cfg["early_keep_days"], now_fn())
    return RoundResult(len(listed), new, len(follow), snapshots)
