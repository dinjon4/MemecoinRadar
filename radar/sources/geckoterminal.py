"""GeckoTerminal: yeni ve hareketli Solana havuzlarını keşfetmek için.

Ücretsiz limit sıkı olduğu için her taramada sadece birkaç liste okunur.
"/new_pools" listesi saniyeler içinde akıp gittiği için (20 havuz ≈ 20 saniye) tek başına yetmez;
bu yüzden hareketli (trend, işlem sayısı, hacim) listeler de okunur. Zaman ölçeğimiz saatler olduğu için
bir tokenı açıldığı anda değil, ilgi görmeye başladığında yakalamak yeterli.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from radar import http
from radar.sources import QUOTE_MINTS

log = logging.getLogger(__name__)

BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json"}

# (yol, parametreler, açıklama)
LISTS = [
    ("/networks/solana/trending_pools", {"duration": "1h"}, "trend 1s"),
    ("/networks/solana/trending_pools", {"duration": "6h"}, "trend 6s"),
    ("/networks/solana/pools", {"sort": "h24_tx_count_desc"}, "işlem sayısı"),
    ("/networks/solana/pools", {"sort": "h24_volume_usd_desc"}, "hacim"),
    ("/networks/solana/new_pools", {}, "yeni"),
]


@dataclass(frozen=True)
class Candidate:
    mint: str
    pool_address: str
    pool_created_at: datetime
    dex: str
    source: str


def parse_pools(payload: dict, source: str) -> list[Candidate]:
    """GeckoTerminal havuz listesi cevabını adaylara çevirir."""
    candidates = []
    for pool in payload.get("data", []):
        try:
            attrs = pool["attributes"]
            rel = pool["relationships"]
            base = rel["base_token"]["data"]["id"].split("_", 1)[1]
            quote = rel["quote_token"]["data"]["id"].split("_", 1)[1]
            created = datetime.fromisoformat(attrs["pool_created_at"].replace("Z", "+00:00"))
            dex = rel["dex"]["data"]["id"]
        except (KeyError, TypeError, ValueError, IndexError):
            log.debug("Ayrıştırılamayan havuz atlandı: %s", pool.get("id"))
            continue
        # Memecoin genelde "base" taraftadır; değilse (ör. SOL/MEME) diğer tarafı al.
        mint = quote if base in QUOTE_MINTS else base
        if mint in QUOTE_MINTS:
            continue
        candidates.append(Candidate(mint, attrs["address"], created, dex, source))
    return candidates


def discover(max_age_hours: int) -> list[Candidate]:
    """Tüm listeleri okur, havuzu max_age_hours'tan yeni olan adayları döner (token başına bir tane).

    Bir liste okunamazsa loga yazılır ve diğerleriyle devam edilir.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    found: dict[str, Candidate] = {}
    for path, params, label in LISTS:
        try:
            payload = http.get(BASE_URL + path, params=params, headers=HEADERS).json()
        except (requests.RequestException, ValueError) as e:
            log.warning("GeckoTerminal '%s' listesi okunamadı: %s", label, type(e).__name__)
            continue
        young = [c for c in parse_pools(payload, label) if c.pool_created_at >= cutoff]
        log.info("GeckoTerminal '%s': %d havuz, %d tanesi son %d saatte açılmış.",
                 label, len(payload.get("data", [])), len(young), max_age_hours)
        for c in young:
            found.setdefault(c.mint, c)
    return list(found.values())
