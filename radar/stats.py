"""Panel için özet sorgular (Genel Bakış sayfası)."""

import sqlite3
from datetime import datetime, timedelta, timezone


def _cutoff(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def overview(conn: sqlite3.Connection, max_age_hours: int, whale_min_usd: float) -> dict:
    """Üst kartlar: izlenen/görülen token, elenen, 24 saatlik whale akışı."""
    cutoff = _cutoff(max_age_hours)
    seen, passed = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(passed), 0) FROM tokens WHERE created_at >= ?", (cutoff,)
    ).fetchone()
    vetoed = conn.execute(
        "SELECT COUNT(DISTINCT r.token) FROM risk_checks r JOIN tokens t ON t.address = r.token "
        "WHERE r.level = 'veto' AND t.passed = 1 AND t.created_at >= ?", (cutoff,)
    ).fetchone()[0]
    flow = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN side = 'buy' THEN usd ELSE -usd END), 0) AS net,
               COALESCE(SUM(CASE WHEN side = 'buy' THEN usd ELSE 0 END), 0)    AS buys,
               COALESCE(SUM(CASE WHEN side = 'sell' THEN usd ELSE 0 END), 0)   AS sells,
               COUNT(*) AS trades
        FROM trades WHERE usd >= ? AND block_time >= ?
        """,
        (whale_min_usd, _cutoff(24)),
    ).fetchone()
    return {"seen": seen, "passed": passed, "vetoed": vetoed, "net_usd": flow["net"],
            "buy_usd": flow["buys"], "sell_usd": flow["sells"], "trades": flow["trades"]}


def hourly_flow(conn: sqlite3.Connection, whale_min_usd: float, hours: int = 24) -> list[dict]:
    """Son `hours` saatin saatlik whale alım, satım ve net akışı (boş saatler 0)."""
    rows = {
        r["hour"]: r
        for r in conn.execute(
            """
            SELECT substr(block_time, 1, 13) AS hour,
                   SUM(CASE WHEN side = 'buy' THEN usd ELSE 0 END)  AS buys,
                   SUM(CASE WHEN side = 'sell' THEN usd ELSE 0 END) AS sells
            FROM trades WHERE usd >= ? AND block_time >= ?
            GROUP BY hour
            """,
            (whale_min_usd, _cutoff(hours)),
        )
    }
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(hours - 1, -1, -1):
        hour = now - timedelta(hours=i)
        r = rows.get(hour.strftime("%Y-%m-%dT%H"))
        buys, sells = (r["buys"], r["sells"]) if r else (0.0, 0.0)
        out.append({"hour": hour, "buys": buys, "sells": sells, "net": buys - sells})
    return out


def top_flows(conn: sqlite3.Connection, max_age_hours: int, whale_min_usd: float, limit: int = 6) -> list[dict]:
    """Whale net akışı en büyük (mutlak) tokenlar."""
    rows = conn.execute(
        """
        SELECT t.address, t.symbol, t.name, t.market_cap_usd, t.liquidity_usd,
               SUM(CASE WHEN tr.side = 'buy' THEN tr.usd ELSE -tr.usd END) AS net,
               COUNT(*) AS trades
        FROM trades tr JOIN tokens t ON t.address = tr.token
        WHERE tr.usd >= ? AND t.passed = 1 AND t.created_at >= ?
        GROUP BY t.address
        ORDER BY ABS(net) DESC LIMIT ?
        """,
        (whale_min_usd, _cutoff(max_age_hours), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_trades(conn: sqlite3.Connection, whale_min_usd: float, limit: int = 6) -> list[dict]:
    rows = conn.execute(
        """
        SELECT tr.block_time, tr.side, tr.usd, tr.wallet, t.symbol, t.address
        FROM trades tr JOIN tokens t ON t.address = tr.token
        WHERE tr.usd >= ? ORDER BY tr.block_time DESC LIMIT ?
        """,
        (whale_min_usd, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_risks(conn: sqlite3.Connection, max_age_hours: int, limit: int = 6) -> list[dict]:
    """En yeni veto ve uyarılar (veto önce)."""
    rows = conn.execute(
        """
        SELECT r.level, r.title, r.updated_at, t.symbol, t.address
        FROM risk_checks r JOIN tokens t ON t.address = r.token
        WHERE r.level IN ('veto', 'warn') AND t.created_at >= ?
        ORDER BY (r.level = 'veto') DESC, r.updated_at DESC LIMIT ?
        """,
        (_cutoff(max_age_hours), limit),
    ).fetchall()
    return [dict(r) for r in rows]
