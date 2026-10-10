"""Erken Hacim: panel için özet (toplanan veriden okunur, internete çıkmaz)."""

import sqlite3
from datetime import datetime, timedelta

# Bir havuzun "son" ölçümü en fazla bu kadar eski olabilir; daha eskiyse havuz listede gösterilmez.
LATEST_MINUTES = 30
# İvme: son 5 dk hacmi ÷ (10–40 dk önceki ölçümlerin 5 dk hacim ortalaması).
BASELINE_FROM_MINUTES, BASELINE_TO_MINUTES = 40, 10


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def counts(conn: sqlite3.Connection, max_age_hours: int, now: datetime) -> dict:
    hour_ago = _iso(now - timedelta(hours=1))
    return {
        "pools": conn.execute("SELECT COUNT(*) FROM ev_pools WHERE created_at >= ?",
                              (_iso(now - timedelta(hours=max_age_hours)),)).fetchone()[0],
        "new_last_hour": conn.execute("SELECT COUNT(*) FROM ev_pools WHERE first_seen_at >= ?",
                                      (hour_ago,)).fetchone()[0],
        "snapshots_last_hour": conn.execute("SELECT COUNT(*) FROM ev_snapshots WHERE taken_at >= ?",
                                            (hour_ago,)).fetchone()[0],
        "snapshots_total": conn.execute("SELECT COUNT(*) FROM ev_snapshots").fetchone()[0],
    }


def _latest(conn: sqlite3.Connection, source: str, since: str) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """SELECT s.* FROM ev_snapshots s
           JOIN (SELECT pool, MAX(taken_at) AS t FROM ev_snapshots
                 WHERE source = ? AND taken_at >= ? GROUP BY pool) l
             ON s.pool = l.pool AND s.taken_at = l.t AND s.source = ?""",
        (source, since, source),
    )
    return {r["pool"]: r for r in rows}


def _baselines(conn: sqlite3.Connection, now: datetime) -> dict[str, float]:
    rows = conn.execute(
        """SELECT pool, AVG(m5_volume) AS avg FROM ev_snapshots
           WHERE source = 'ds' AND taken_at >= ? AND taken_at < ? AND m5_volume IS NOT NULL
           GROUP BY pool""",
        (_iso(now - timedelta(minutes=BASELINE_FROM_MINUTES)), _iso(now - timedelta(minutes=BASELINE_TO_MINUTES))),
    )
    return {r["pool"]: r["avg"] for r in rows}


def acceleration(current: float | None, baseline: float | None) -> float | None:
    """Son 5 dk hacmi, önceki ortalamanın kaç katı. Önceki ölçüm yoksa veya hacim sıfırsa None."""
    if current is None or not baseline:
        return None
    return current / baseline


def pools(conn: sqlite3.Connection, max_age_hours: int, now: datetime) -> list[dict]:
    """Son ölçümü taze olan havuzlar; en yüksek 5 dk hacmi önce.

    Hacim, alım/satım ve likidite DexScreener ölçümünden (yoksa GeckoTerminal'den);
    benzersiz alıcı sayısı sadece GeckoTerminal listelerinde görülen havuzlar için var.
    """
    since = _iso(now - timedelta(minutes=LATEST_MINUTES))
    ds, gt = _latest(conn, "ds", since), _latest(conn, "gt", since)
    base = _baselines(conn, now)
    meta = conn.execute("SELECT * FROM ev_pools WHERE created_at >= ?",
                        (_iso(now - timedelta(hours=max_age_hours)),)).fetchall()
    result = []
    for p in meta:
        main = ds.get(p["pool"]) or gt.get(p["pool"])
        if main is None:
            continue
        g = gt.get(p["pool"])
        age_min = (now - datetime.fromisoformat(p["created_at"])).total_seconds() / 60
        result.append({
            "pool": p["pool"], "token": p["token"], "symbol": p["symbol"] or "", "name": p["name"] or "",
            "dex": p["dex"], "url": p["url"], "source": p["source"], "age_minutes": age_min,
            "measured_at": main["taken_at"],
            "price_usd": main["price_usd"], "market_cap_usd": main["market_cap_usd"],
            # Bonding curve havuzlarında DexScreener likidite vermiyor; GeckoTerminal'in değeri kullanılır.
            "liquidity_usd": main["liquidity_usd"] if main["liquidity_usd"] is not None
            else (g["liquidity_usd"] if g else None),
            "m5_volume": main["m5_volume"], "m5_buys": main["m5_buys"], "m5_sells": main["m5_sells"],
            "h1_volume": main["h1_volume"],
            "m5_buyers": g["m5_buyers"] if g else None,
            "m15_buyers": g["m15_buyers"] if g else None,
            "acceleration": acceleration(ds[p["pool"]]["m5_volume"], base.get(p["pool"]))
            if p["pool"] in ds else None,
        })
    result.sort(key=lambda r: r["m5_volume"] or 0, reverse=True)
    return result
