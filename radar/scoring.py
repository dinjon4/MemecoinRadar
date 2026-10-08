"""Aşama 4: 0–100 skor.

Skor = whale net akışı + alıcı çeşitliliği + likidite/MC oranı (ağırlıklar config'den, toplam 100)
       − her risk uyarısı için ceza.
Veto alan tokenın skoru hesaplanmaz. Her bileşen 0–1 arası bir oran üretir; ağırlıkla çarpılır.
Sonuç ve nedenleri `scores` tablosuna yazılır (panel ve Telegram mesajı buradan okur).
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass

from radar import db, flows, risk

log = logging.getLogger(__name__)

# Bileşen sınırları: bu değerlerde oran 0, şu değerlerde 1 olur (arası doğrusal).
FLOW_FULL_RATIO = 0.5        # whale net girişi likiditenin %50'si → tam puan
BUYERS_FULL = 8              # 8 bağımsız whale alıcı (grup) → tam puan
LIQ_MC_ZERO, LIQ_MC_FULL = 0.03, 0.20


@dataclass
class Score:
    token: str
    score: int
    flow_points: float
    buyers_points: float
    liquidity_points: float
    penalty: float
    net_usd: float
    buyers: int           # net alım yapan whale cüzdan sayısı
    buyer_groups: int     # aynı saniyede alanlar tek grup sayılınca
    warn_titles: list[str]
    ok_titles: list[str]


def _ratio(value: float, zero: float, full: float) -> float:
    if value <= zero:
        return 0.0
    if value >= full:
        return 1.0
    return (value - zero) / (full - zero)


def buyer_groups(conn: sqlite3.Connection, token: str, whale_min_usd: float) -> tuple[int, int]:
    """Net alım yapan whale cüzdanları ve bunların 'grup' sayısı.

    Aynı saniyede alım yapan cüzdanlar tek grup sayılır (toplu alım = büyük ihtimalle tek kişi).
    """
    rows = conn.execute(
        """
        SELECT wallet, SUM(CASE WHEN side = 'buy' THEN usd ELSE -usd END) AS net,
               MIN(CASE WHEN side = 'buy' THEN block_time END) AS first_buy
        FROM trades WHERE token = ? AND usd >= ?
        GROUP BY wallet HAVING net > 0
        """,
        (token, whale_min_usd),
    ).fetchall()
    groups = {r["first_buy"] for r in rows if r["first_buy"]}
    return len(rows), len(groups)


def compute(conn: sqlite3.Connection, cfg: dict, token: sqlite3.Row) -> Score | None:
    """Tokenın skoru. Veto aldıysa None."""
    checks = risk.checks_for(conn, token["address"])
    if any(c["level"] == "veto" for c in checks):
        return None
    whale_min = cfg["whale_min_usd"]
    summary = flows.token_summary(conn, token["address"], whale_min)
    liquidity = token["liquidity_usd"] or 0.0
    mc = token["market_cap_usd"] or 0.0

    flow_ratio = _ratio(summary["net_usd"] / liquidity, 0.0, FLOW_FULL_RATIO) if liquidity > 0 else 0.0
    buyers, groups = buyer_groups(conn, token["address"], whale_min)
    buyers_ratio = min(groups / BUYERS_FULL, 1.0)
    liq_ratio = _ratio(liquidity / mc, LIQ_MC_ZERO, LIQ_MC_FULL) if mc > 0 else 0.0

    warns = [c["title"] for c in checks if c["level"] == "warn"]
    oks = [c["title"] for c in checks if c["level"] == "ok"]
    penalty = cfg["risk_warn_penalty"] * len(warns)

    flow_pts = cfg["score_weights.whale_net_flow"] * flow_ratio
    buyer_pts = cfg["score_weights.buyer_diversity"] * buyers_ratio
    liq_pts = cfg["score_weights.liquidity_to_mc"] * liq_ratio
    total = round(max(0.0, min(100.0, flow_pts + buyer_pts + liq_pts - penalty)))
    return Score(token["address"], total, round(flow_pts, 1), round(buyer_pts, 1), round(liq_pts, 1),
                 penalty, summary["net_usd"], buyers, groups, warns, oks)


def save(conn: sqlite3.Connection, s: Score) -> None:
    conn.execute(
        "INSERT INTO scores (token, score, details, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(token) DO UPDATE SET score = excluded.score, details = excluded.details, "
        "updated_at = excluded.updated_at",
        (s.token, s.score, json.dumps(asdict(s), ensure_ascii=False), db.utc_now()),
    )


def load(conn: sqlite3.Connection, token: str) -> Score | None:
    row = conn.execute("SELECT details FROM scores WHERE token = ?", (token,)).fetchone()
    return Score(**json.loads(row["details"])) if row else None


def breakdown(s: Score, cfg: dict) -> str:
    """Skorun nedenleri, tek satır: 'whale akışı 40/50 · alıcılar 15/30 · likidite 20/20 · risk −8'."""
    parts = [
        f"whale akışı {s.flow_points:g}/{cfg['score_weights.whale_net_flow']}",
        f"alıcılar {s.buyers_points:g}/{cfg['score_weights.buyer_diversity']}",
        f"likidite {s.liquidity_points:g}/{cfg['score_weights.liquidity_to_mc']}",
    ]
    if s.penalty:
        parts.append(f"risk −{s.penalty:g}")
    return " · ".join(parts)
