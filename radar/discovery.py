"""Aşama 1: yeni token tespiti.

1. GeckoTerminal listelerinden son X saatte açılmış havuzların tokenlarını bul (keşif).
2. Bunları ve daha önce bulunup hâlâ yeterince yeni olan tokenları DexScreener'dan güncelle.
3. Yaş, likidite ve bonding curve filtrelerini uygula; sonucu (elenenler dahil) veritabanına yaz.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from radar import db
from radar.sources import BONDING_CURVE_DEXES, dexscreener, geckoterminal

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    discovered: int    # bu taramada keşif listelerinde görülen aday sayısı
    new: int           # ilk kez görülenler
    checked: int       # DexScreener'dan güncellenen
    passed: list[dexscreener.TokenInfo]


def filter_reason(info: dexscreener.TokenInfo, cfg: dict, now: datetime) -> str | None:
    """Token elenecekse Türkçe sebebi, geçiyorsa None döner."""
    if info.created_at is None:
        return "açılış zamanı bilinmiyor"
    age = now - info.created_at
    if age > timedelta(hours=cfg["token_max_age_hours"]):
        return f"çok eski ({age.total_seconds() / 3600:.0f} saat)"
    if not cfg["include_bonding_curve"] and info.dex in BONDING_CURVE_DEXES:
        return f"bonding curve aşamasında ({info.dex})"
    if info.liquidity_usd < cfg["min_liquidity_usd"]:
        return f"likidite düşük (${info.liquidity_usd:,.0f})"
    return None


def _tracked_mints(conn: sqlite3.Connection, max_age_hours: int, now: datetime) -> list[str]:
    """Daha önce bulunmuş ve hâlâ yaş sınırı içindeki tokenlar (yeniden kontrol edilecek)."""
    cutoff = (now - timedelta(hours=max_age_hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT address FROM tokens WHERE created_at >= ? OR created_at IS NULL", (cutoff,)
    )
    return [r["address"] for r in rows]


def _save(conn: sqlite3.Connection, info: dexscreener.TokenInfo, source: str | None,
          reason: str | None, now_iso: str) -> bool:
    """Tokenı ekler veya günceller. İlk kez görüldüyse True döner."""
    is_new = conn.execute("SELECT 1 FROM tokens WHERE address = ?", (info.mint,)).fetchone() is None
    conn.execute(
        """
        INSERT INTO tokens (address, name, symbol, created_at, first_seen_at, updated_at, source,
                            pair_address, dex, url, price_usd, market_cap_usd, liquidity_usd,
                            volume_h24_usd, buys_h24, sells_h24, passed, filter_reason,
                            quote_mint, quote_price_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            name = excluded.name, symbol = excluded.symbol, created_at = excluded.created_at,
            updated_at = excluded.updated_at, pair_address = excluded.pair_address, dex = excluded.dex,
            url = excluded.url, price_usd = excluded.price_usd, market_cap_usd = excluded.market_cap_usd,
            liquidity_usd = excluded.liquidity_usd, volume_h24_usd = excluded.volume_h24_usd,
            buys_h24 = excluded.buys_h24, sells_h24 = excluded.sells_h24,
            passed = excluded.passed, filter_reason = excluded.filter_reason,
            quote_mint = excluded.quote_mint, quote_price_usd = excluded.quote_price_usd
        """,
        (
            info.mint, info.name, info.symbol,
            info.created_at.isoformat(timespec="seconds") if info.created_at else None,
            now_iso, now_iso, source, info.pair_address, info.dex, info.url, info.price_usd,
            info.market_cap_usd, info.liquidity_usd, info.volume_h24_usd, info.buys_h24,
            info.sells_h24, 0 if reason else 1, reason, info.quote_mint, info.quote_price_usd,
        ),
    )
    return is_new


def scan(conn: sqlite3.Connection, cfg: dict) -> ScanResult:
    now = datetime.now(timezone.utc)
    max_age = cfg["token_max_age_hours"]

    candidates = {c.mint: c for c in geckoterminal.discover(max_age)}
    mints = list(dict.fromkeys(list(candidates) + _tracked_mints(conn, max_age, now)))
    infos = dexscreener.fetch_tokens(mints)
    missing = len(mints) - len(infos)
    if missing:
        log.info("%d token DexScreener'da bulunamadı, atlandı.", missing)

    now_iso = db.utc_now()
    new_count, passed = 0, []
    for mint, info in infos.items():
        reason = filter_reason(info, cfg, now)
        source = candidates[mint].source if mint in candidates else None
        if _save(conn, info, source, reason, now_iso):
            new_count += 1
        if reason is None:
            passed.append(info)
    conn.commit()

    passed.sort(key=lambda i: i.created_at, reverse=True)
    log.info("Tarama: %d aday, %d yeni, %d kontrol edildi, %d token filtreleri geçti.",
             len(candidates), new_count, len(infos), len(passed))
    return ScanResult(len(candidates), new_count, len(infos), passed)


def format_table(tokens: list[dexscreener.TokenInfo], now: datetime | None = None) -> str:
    """Terminal için basit tablo."""
    if not tokens:
        return "Filtreleri geçen token yok."
    now = now or datetime.now(timezone.utc)
    lines = [f"{'SEMBOL':<12} {'İSİM':<24} {'YAŞ':>7} {'MC':>10} {'LİKİDİTE':>10}  DEX"]
    for t in tokens:
        hours = (now - t.created_at).total_seconds() / 3600
        lines.append(
            f"{t.symbol[:12]:<12} {t.name[:24]:<24} {hours:>4.1f} sa {_usd(t.market_cap_usd):>10} "
            f"{_usd(t.liquidity_usd):>10}  {t.dex}"
        )
    return "\n".join(lines)


def _usd(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:.0f}"
