"""Aşama 6: haber / hikâye katmanı.

Memecoinler çoğu zaman bir habere, trende veya viral bir olaya dayanır ("hikâye").
Ücretsiz akışlar (RSS/Atom) okunur, başlıklar saklanır ve token adı/sembolüyle eşleştirilir.
Eşleşme bulunursa Telegram mesajına ve panele "Hikâye: ..." satırı eklenir. Skoru etkilemez
(etkisi Aşama 5 verisiyle ölçüldükten sonra karar verilecek).

X (Twitter) verisi ücretli olduğu için yok. Reddit'in JSON API'si kayıt istiyor; RSS kullanılıyor.
"""

import hashlib
import html
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from defusedxml import ElementTree as ET

from radar import db, http

log = logging.getLogger(__name__)

# (kısa ad, adres, açıklama) — 2026-10-08'de hepsi denendi ve çalışıyordu.
SOURCES = [
    ("Google Trends", "https://trends.google.com/trending/rss?geo=US", "ABD'de günün trend aramaları"),
    ("Google News", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", "ABD manşetleri"),
    ("Reddit", "https://www.reddit.com/r/all/.rss", "Reddit'te şu an popüler olanlar"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "kripto haberleri"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "kripto haberleri"),
    ("Decrypt", "https://decrypt.co/feed", "kripto haberleri"),
    ("The Block", "https://www.theblock.co/rss.xml", "kripto haberleri"),
]

KEEP_HOURS = 96  # bu kadar eski haberler silinir

# Tek başına eşleşmeye yetmeyen kelimeler (küçük harf):
# 1) İngilizcede çok sık geçenler (radar/data/common_words_en.txt, ~4.300 kelime; ör. "have", "test", "markets"),
# 2) kripto/memecoin jargonu (aşağıda).
COMMON_WORDS = {
    line.strip() for line in (Path(__file__).parent / "data" / "common_words_en.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}
STOPWORDS = {
    "coin", "coins", "token", "tokens", "crypto", "solana", "sol", "meme", "memes", "memecoin", "pump",
    "moon", "inu", "doge", "pepe", "cat", "dog", "frog", "bonk", "elon", "trump", "base", "chain",
    "finance", "network", "protocol", "labs", "dao", "swap", "ai", "agent", "bitcoin", "btc", "eth",
    "ethereum", "usd", "usdt", "usdc", "wif", "gpt", "launch", "fun", "bags", "market", "price",
}
MIN_WORD_LEN = 4


@dataclass(frozen=True)
class Item:
    source: str
    title: str
    url: str
    published: datetime
    text: str  # eşleştirmede kullanılan metin (başlık + ilgili haber başlıkları)


# --- Okuma ---

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el, name: str) -> str:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _parse_date(text: str) -> datetime | None:
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(source: str, xml_text: str, now: datetime | None = None) -> list[Item]:
    """RSS veya Atom akışını okur. Tarihi olmayan öğelere okuma zamanı verilir."""
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(xml_text)
    items = []
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ("item", "entry"):
            continue
        title = _child_text(el, "title")
        if not title:
            continue
        url = _child_text(el, "link")
        if not url:  # Atom: <link href="..."/>
            for c in el:
                if _local(c.tag) == "link" and c.get("href"):
                    url = c.get("href")
                    break
        published = _parse_date(_child_text(el, "pubDate") or _child_text(el, "published")
                                or _child_text(el, "updated")) or now
        # Google Trends: trend kelimesinin yanında ilgili haber başlıkları da var.
        related = [(c.text or "").strip() for c in el.iter() if _local(c.tag) == "news_item_title"]
        # Satır satır saklanır: eşleşme hangi satırdaysa (trend mi, ilgili haber mi) o gösterilir.
        items.append(Item(source, html.unescape(title), url, published,
                          "\n".join([html.unescape(title), *(html.unescape(r) for r in related if r)])))
    return items


def fetch_all() -> list[Item]:
    items = []
    for source, url, _ in SOURCES:
        try:
            text = http.get(url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml"}).text
            got = parse_feed(source, text)
        except (requests.RequestException, ET.ParseError, ValueError) as e:
            log.warning("Haber kaynağı okunamadı (%s): %s", source, type(e).__name__)
            continue
        items += got
    return items


def update(conn: sqlite3.Connection) -> int:
    """Kaynakları okuyup yeni haberleri kaydeder, eskileri siler. Yeni haber sayısını döner."""
    items = fetch_all()
    before = conn.total_changes
    for it in items:
        key = hashlib.sha1(f"{it.source}|{it.title}|{it.url}".encode()).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO news (id, source, title, url, published_at, fetched_at, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, it.source, it.title, it.url, it.published.isoformat(timespec="seconds"), db.utc_now(), it.text),
        )
    added = conn.total_changes - before
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=KEEP_HOURS)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM news WHERE published_at < ?", (cutoff,))
    conn.commit()
    log.info("Haberler: %d kaynaktan %d başlık okundu, %d yeni.", len(SOURCES), len(items), added)
    return added


# --- Eşleştirme ---

def _normalize(text: str) -> str:
    """Küçük harf, aksan/benzer harf sadeleştirme, sadece harf-rakam ve boşluk."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def distinctive(word: str) -> bool:
    """Tek başına eşleşmeye yetecek kadar ayırt edici mi? (yeterince uzun, yaygın değil, sayı değil)"""
    return (len(word) >= MIN_WORD_LEN and not word.isdigit()
            and word not in COMMON_WORDS and word not in STOPWORDS)


def keywords(symbol: str, name: str) -> list[str]:
    """Tokenın haberde aranacak ifadeleri: tam isim (2+ kelimeyse) ve ayırt edici tek kelimeler."""
    out = []
    norm_name = _normalize(name)
    words = norm_name.split()
    meaningful = [w for w in words if distinctive(w)]
    if len(words) >= 2 and meaningful:
        out.append(norm_name)  # "shark tank", "capybara with a gun"
    out += meaningful
    sym = _normalize(symbol)
    if " " not in sym and distinctive(sym):
        out.append(sym)
    # Sırayı koruyarak tekrarları at.
    return list(dict.fromkeys(out))


def age_text(published_at: str) -> str:
    hours = (datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600
    if hours < 1:
        return f"{max(1, round(hours * 60))} dk önce"
    if hours < 48:
        return f"{hours:.0f} saat önce"
    return f"{hours / 24:.0f} gün önce"


@dataclass(frozen=True)
class Match:
    source: str
    title: str          # eşleşen satır (haber başlığı)
    url: str
    published_at: str
    keyword: str
    context: str = ""   # eşleşme bir trendin altındaki haberdeyse trendin kendisi (ör. Google Trends araması)


def find(conn: sqlite3.Connection, symbol: str, name: str, created_at: str | None,
         lookback_hours: int, limit: int = 3) -> list[Match]:
    """Token için eşleşen haberler; en uzun (en ayırt edici) ifade ve en yeni haber önce.

    Sadece tokenın çıkışından en fazla `lookback_hours` önce ve sonrasında yayınlanan haberlere bakılır.
    """
    kws = keywords(symbol, name)
    if not kws:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    if created_at:
        since = min(since, datetime.fromisoformat(created_at) - timedelta(hours=lookback_hours))
    rows = conn.execute(
        "SELECT * FROM news WHERE published_at >= ? ORDER BY published_at DESC",
        (since.isoformat(timespec="seconds"),),
    ).fetchall()
    patterns = [(kw, re.compile(rf"\b{re.escape(kw)}\b")) for kw in sorted(kws, key=len, reverse=True)]
    matches = []
    seen_titles = set()
    for r in rows:
        lines = r["text"].split("\n")
        hit = next(((kw, line) for kw, pat in patterns for line in lines if pat.search(_normalize(line))), None)
        if hit is None:
            continue
        kw, line = hit
        if line in seen_titles:
            continue
        seen_titles.add(line)
        context = r["title"] if line != r["title"] else ""
        matches.append((len(kw), Match(r["source"], line, r["url"], r["published_at"], kw, context)))
    # En uzun (en ayırt edici) ifade önce; eşitse en yeni haber önce.
    best = sorted(matches, key=lambda m: (m[0], m[1].published_at), reverse=True)
    return [m for _, m in best[:limit]]
