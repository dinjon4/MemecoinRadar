"""Aşama 5: takip ve haftalık özet.

Amaç: skor gerçekten işe yarıyor mu? Bunun için uyarı verilen tokenlar ile uyarı verilmeyenler
(karşılaştırma grubu) aynı şekilde izlenir ve 1, 6, 24 saat sonraki durumları kaydedilir.

Gruplar (cohort):
- alert : uyarı gönderilen her token (ilk uyarı anından itibaren)
- low   : skoru eşiğin altında kalanlardan rastgele bir kısmı
- veto  : risk kontrolünden elenenlerden rastgele bir kısmı
"Rastgele" seçim adrese göre sabittir (aynı token her turda aynı karara varır).
"""

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from radar import db, notify
from radar.sources import dexscreener

log = logging.getLogger(__name__)

CHECKPOINTS = (1, 6, 24)          # saat
COHORTS = {"alert": "Uyarı verilenler", "low": "Düşük skorlular", "veto": "Riskten elenenler"}
RUGGED_LIQUIDITY_USD = 1_000      # bu altı likidite = havuz boşaltılmış sayılır
TZ = ZoneInfo("Europe/Istanbul")


# --- Gruba ekleme ---

def in_sample(address: str, pct: int) -> bool:
    """Adrese göre sabit 'rastgele' seçim: tokenların yaklaşık %pct'si seçilir."""
    return int(hashlib.sha256(address.encode()).hexdigest()[:8], 16) % 100 < pct


def start(conn: sqlite3.Connection, token: sqlite3.Row, cohort: str, score: int | None) -> bool:
    """Tokenı gruba ekler (o grupta zaten varsa eklemez). Eklendiyse True."""
    exists = conn.execute("SELECT 1 FROM tracking WHERE token = ? AND cohort = ?",
                          (token["address"], cohort)).fetchone()
    if exists:
        return False
    conn.execute(
        "INSERT INTO tracking (token, cohort, score, started_at, price_0, mc_0, liq_0) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (token["address"], cohort, score, db.utc_now(), token["price_usd"], token["market_cap_usd"], token["liquidity_usd"]),
    )
    return True


def add_controls(conn: sqlite3.Connection, cfg: dict, scored: list[tuple[sqlite3.Row, int | None]]) -> int:
    """Skor turunda uyarı almayan tokenlardan karşılaştırma grubunu seçer.

    scored: (token, skor) listesi; skor None = veto.
    """
    added = 0
    for token, score in scored:
        if score is not None and score >= cfg["min_score_to_alert"]:
            continue
        if not in_sample(token["address"], cfg["control_sample_pct"]):
            continue
        cohort = "veto" if score is None else "low"
        added += start(conn, token, cohort, score)
    return added


# --- 1/6/24 saat ölçümleri ---

def due_checkpoints(conn: sqlite3.Connection, now: datetime) -> list[tuple[sqlite3.Row, int]]:
    due = []
    for row in conn.execute("SELECT * FROM tracking WHERE done = 0"):
        started = datetime.fromisoformat(row["started_at"])
        for h in CHECKPOINTS:
            if row[f"checked_{h}h"] is None and now >= started + timedelta(hours=h):
                due.append((row, h))
    return due


def update(conn: sqlite3.Connection) -> int:
    """Zamanı gelmiş ölçümleri DexScreener'dan yapar. Yapılan ölçüm sayısını döner.

    Bilgisayar uyuduysa ölçüm geç yapılır; gerçek ölçüm zamanı checked_*h sütununda durur.
    """
    now = datetime.now(timezone.utc)
    due = due_checkpoints(conn, now)
    if not due:
        return 0
    infos = dexscreener.fetch_tokens(list({row["token"] for row, _ in due}))
    now_iso = db.utc_now()
    for row, h in due:
        info = infos.get(row["token"])
        # DexScreener'da hiç havuzu kalmadıysa: fiyat bilinmiyor, likidite 0 (boşaltılmış).
        price = info.price_usd if info else None
        mc = info.market_cap_usd if info else None
        liq = info.liquidity_usd if info else 0.0
        conn.execute(
            f"UPDATE tracking SET price_{h}h = ?, mc_{h}h = ?, liq_{h}h = ?, checked_{h}h = ?, "
            f"done = ? WHERE id = ?",
            (price, mc, liq, now_iso, int(h == CHECKPOINTS[-1]), row["id"]),
        )
    conn.commit()
    log.info("Takip: %d ölçüm yapıldı.", len(due))
    return len(due)


# --- Sonuçlar ---

def change(start_value: float | None, end_value: float | None) -> float | None:
    """Yüzde değişim; hesaplanamıyorsa None."""
    if not start_value or end_value is None:
        return None
    return 100 * (end_value / start_value - 1)


def outcome(row, cfg: dict, h: int = 24) -> str | None:
    """'up' / 'crash' / 'flat'; ölçüm yoksa None."""
    if row[f"checked_{h}h"] is None:
        return None
    if (row[f"liq_{h}h"] or 0) < RUGGED_LIQUIDITY_USD:
        return "crash"
    pct = change(row["mc_0"], row[f"mc_{h}h"])
    if pct is None:
        pct = change(row["price_0"], row[f"price_{h}h"])
    if pct is None:
        return None
    if pct >= cfg["outcome_up_pct"]:
        return "up"
    if pct <= -cfg["outcome_crash_pct"]:
        return "crash"
    return "flat"


@dataclass
class CohortStats:
    cohort: str
    tracked: int        # gruptaki toplam token
    finished: int       # 24 saat ölçümü yapılmış
    up: int
    crash: int
    flat: int
    median_change: float | None   # 24 saatteki MC değişimlerinin ortancası (%)

    def pct(self, n: int) -> float | None:
        return 100 * n / self.finished if self.finished else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def cohort_stats(conn: sqlite3.Connection, cfg: dict, since: str | None = None) -> dict[str, CohortStats]:
    """Grup başına sonuçlar. since verilirse sadece o tarihten sonra başlayan takipler."""
    rows = conn.execute(
        "SELECT * FROM tracking" + (" WHERE started_at >= ?" if since else ""), (since,) if since else ()
    ).fetchall()
    out = {}
    for cohort in COHORTS:
        group = [r for r in rows if r["cohort"] == cohort]
        results = [outcome(r, cfg) for r in group]
        changes = [c for r in group if r["checked_24h"] and (c := change(r["mc_0"], r["mc_24h"])) is not None]
        out[cohort] = CohortStats(
            cohort, len(group), sum(x is not None for x in results),
            results.count("up"), results.count("crash"), results.count("flat"), _median(changes),
        )
    return out


def score_buckets(conn: sqlite3.Connection, cfg: dict) -> list[dict]:
    """Skor aralığına göre 24 saat sonuçları (veto hariç)."""
    buckets = [("80–100", 80, 101), ("70–79", 70, 80), ("60–69", 60, 70), ("40–59", 40, 60), ("0–39", 0, 40)]
    rows = conn.execute("SELECT * FROM tracking WHERE score IS NOT NULL AND checked_24h IS NOT NULL").fetchall()
    out = []
    for label, lo, hi in buckets:
        group = [r for r in rows if lo <= r["score"] < hi]
        results = [outcome(r, cfg) for r in group]
        changes = [c for r in group if (c := change(r["mc_0"], r["mc_24h"])) is not None]
        out.append({"label": label, "n": len(group), "up": results.count("up"), "crash": results.count("crash"),
                    "median_change": _median(changes)})
    return out


# --- Haftalık özet ---

def weekly_message(conn: sqlite3.Connection, cfg: dict) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    stats = cohort_stats(conn, cfg, since)
    lines = ["📊 <b>Memecoin Radar — haftalık özet</b>",
             f"<i>Son 7 gün · 24 saat sonra: yükseldi = MC +%{cfg['outcome_up_pct']}+, "
             f"çöktü = MC −%{cfg['outcome_crash_pct']} veya likidite boşaltıldı</i>", ""]
    for cohort, label in COHORTS.items():
        s = stats[cohort]
        if not s.finished:
            lines.append(f"<b>{label}</b>: henüz 24 saati dolan yok ({s.tracked} izleniyor)")
            continue
        median = f"{s.median_change:+.0f}%" if s.median_change is not None else "—"
        lines.append(f"<b>{label}</b> ({s.finished} token): 🟢 %{s.pct(s.up):.0f} yükseldi · "
                     f"🔴 %{s.pct(s.crash):.0f} çöktü · ortanca {median}")
    alert, low = stats["alert"], stats["low"]
    lines.append("")
    if alert.finished >= 5 and low.finished >= 5:
        diff = alert.pct(alert.up) - low.pct(low.up)
        verdict = "daha iyi" if diff > 5 else "daha kötü" if diff < -5 else "benzer"
        lines.append(f"➡️ Uyarılar, düşük skorlulara göre <b>{verdict}</b> "
                     f"(yükselme oranı farkı {diff:+.0f} puan).")
    else:
        lines.append("➡️ Karşılaştırma için henüz yeterli veri yok (her grupta en az 5 token gerekli).")

    reasons = conn.execute(
        """
        SELECT r.title, COUNT(*) AS n FROM risk_checks r
        WHERE r.level = 'veto' AND r.updated_at >= ? GROUP BY r.check_key ORDER BY n DESC LIMIT 3
        """,
        (since,),
    ).fetchall()
    if reasons:
        lines.append("En sık eleme sebepleri: " + ", ".join(f"{notify.escape(r['title'])} ({r['n']})" for r in reasons))
    return "\n".join(lines)


def is_weekly_due(cfg: dict, last_sent: str | None, now: datetime) -> bool:
    """Ayarlanan gün ve saat geçtiyse ve bu hafta henüz gönderilmediyse."""
    local = now.astimezone(TZ)
    # Bu haftanın ayarlanan gün/saati (1 = Pazartesi).
    target = (local - timedelta(days=local.isoweekday() - cfg["weekly_summary_day"])).replace(
        hour=cfg["weekly_summary_hour"], minute=0, second=0, microsecond=0)
    if target > local:
        target -= timedelta(days=7)
    return last_sent is None or datetime.fromisoformat(last_sent) < target


def maybe_weekly(conn: sqlite3.Connection, cfg: dict) -> bool:
    if not cfg["weekly_summary_enabled"]:
        return False
    if not is_weekly_due(cfg, db.get_status(conn).get("last_weekly_at"), datetime.now(timezone.utc)):
        return False
    try:
        delivered = notify.send(weekly_message(conn, cfg), cfg)
    except notify.TelegramNotConfigured:
        return False
    if delivered:
        db.set_status(conn, "last_weekly_at", db.utc_now())
        log.info("Haftalık özet gönderildi.")
    return delivered


def summary_line(s: CohortStats) -> str:
    """Panel için kısa açıklama."""
    if not s.finished:
        return f"{s.tracked} izleniyor, 24 saati dolan yok"
    median = f"{s.median_change:+.0f}%" if s.median_change is not None else "—"
    return f"{s.finished} sonuçlandı · ortanca {median} · {s.tracked - s.finished} sürüyor"

