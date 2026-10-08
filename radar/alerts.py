"""Aşama 4: skor hesaplama turu ve Telegram uyarıları.

- Veto almamış, risk kontrolü yapılmış, hâlâ yeni tokenların skoru hesaplanır.
- Skor min_score_to_alert ve üstüyse uyarı gönderilir.
- Aynı token için alert_cooldown_hours dolmadan tekrar uyarı gitmez; skor realert_score_jump kadar
  arttıysa beklemeden tekrar gider.
- Deneme modunda (dry_run) mesaj Telegram'a gitmez ama uyarı kaydedilir (bekleme süresi yine işler).
"""

import html
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from radar import db, fmt, news, notify, risk, scoring, tracking
from radar.notify import escape as e
from radar.sources import helius

log = logging.getLogger(__name__)

STRONG_SCORE = 75  # bu ve üstü 🟢, altı 🟡


def last_alert(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM alerts WHERE token = ? ORDER BY sent_at DESC LIMIT 1", (token,)
    ).fetchone()


def should_alert(cfg: dict, score: int, previous: sqlite3.Row | None, now: datetime) -> tuple[bool, str]:
    """(gönderilsin mi, sebep)."""
    if score < cfg["min_score_to_alert"]:
        return False, f"skor {score} < {cfg['min_score_to_alert']}"
    if previous is None:
        return True, "ilk uyarı"
    since = now - datetime.fromisoformat(previous["sent_at"])
    if score >= previous["score"] + cfg["realert_score_jump"]:
        return True, f"skor yükseldi ({previous['score']} → {score})"
    if since >= timedelta(hours=cfg["alert_cooldown_hours"]):
        return True, "bekleme süresi doldu"
    return False, f"bekleme süresi dolmadı ({since.total_seconds() / 3600:.1f}/{cfg['alert_cooldown_hours']} saat)"


def format_message(conn: sqlite3.Connection, cfg: dict, token: sqlite3.Row, s: scoring.Score,
                   previous: sqlite3.Row | None = None) -> str:
    """Telegram HTML mesajı. Sonuna notify.send() 'Yatırım tavsiyesi değildir' ekler."""
    age = None
    if token["created_at"]:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(token["created_at"])).total_seconds() / 3600
    icon = "🟢" if s.score >= STRONG_SCORE else "🟡"
    symbol = "$" + (token["symbol"] or "?").lstrip("$")

    lines = []
    if previous is not None and s.score > previous["score"]:
        lines.append(f"🔁 Skor yükseldi: {previous['score']} → {s.score}")
    lines += [
        f"{icon} <b>{e(symbol)}</b> — Skor {s.score}/100",
        f"<i>{e(token['name'])}</i>",
        f"MC: {fmt.usd(token['market_cap_usd'])} | Likidite: {fmt.usd(token['liquidity_usd'])} | Yaş: {fmt.hours(age)}",
    ]
    if s.buyers:
        group_note = f", {s.buyer_groups} grup" if s.buyer_groups != s.buyers else ""
        lines.append(f"Whale net akış: {fmt.usd(s.net_usd, signed=True)} ({s.buyers} alıcı cüzdan{group_note})")
    else:
        lines.append(f"Whale net akış: {fmt.usd(s.net_usd, signed=True)}")
    lines.append(f"<i>Skor: {e(scoring.breakdown(s, cfg))}</i>")

    lines += [f"⚠️ {e(t)}" for t in s.warn_titles]
    checks = {c["check_key"]: c for c in risk.checks_for(conn, token["address"])}
    for key in ("dev_sold", "mint_authority", "freeze_authority", "lp_lock"):
        c = checks.get(key)
        if c is not None and c["level"] == "ok":
            lines.append(f"✅ {e(c['title'])}")

    if cfg["news_enabled"]:
        story = news.find(conn, token["symbol"] or "", token["name"] or "", token["created_at"],
                          cfg["news_lookback_hours"], limit=1)
        if story:
            m = story[0]
            trend = f", trend: {e(m.context)}" if m.context else ""
            link = f'<a href="{html.escape(m.url, quote=True)}">{e(m.title)}</a>' if m.url else e(m.title)
            lines.append(f"📰 Hikâye: {link} ({e(m.source)}{trend}, {news.age_text(m.published_at)})")

    lines.append(f"<code>{e(token['address'])}</code>")
    links = []
    if token["url"]:
        links.append(f'<a href="{html.escape(token["url"], quote=True)}">DexScreener</a>')
    x_url = f"https://x.com/search?q={quote(token['address'])}&f=live"
    links.append(f'<a href="{html.escape(x_url, quote=True)}">X\'te ara</a>')
    lines.append(" · ".join(links))
    return "\n".join(lines)


def tokens_to_score(conn: sqlite3.Connection, cfg: dict) -> list[sqlite3.Row]:
    """Filtreyi geçmiş, hâlâ yeni ve risk kontrolü yapılmış tokenlar."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=cfg["token_max_age_hours"])).isoformat(timespec="seconds")
    return conn.execute(
        "SELECT * FROM tokens WHERE passed = 1 AND created_at >= ? "
        "AND address IN (SELECT token FROM risk_checks) ORDER BY volume_h24_usd DESC",
        (cutoff,),
    ).fetchall()


def run(conn: sqlite3.Connection, cfg: dict) -> int:
    """Skorları günceller, gereken uyarıları gönderir ve takip gruplarını günceller.
    Gönderilen uyarı sayısını döner."""
    now = datetime.now(timezone.utc)
    sent = 0
    telegram_ok = True
    scored: list[tuple[sqlite3.Row, int | None]] = []  # karşılaştırma grubu seçimi için
    for token in tokens_to_score(conn, cfg):
        s = scoring.compute(conn, cfg, token)
        if s is None:
            conn.execute("DELETE FROM scores WHERE token = ?", (token["address"],))
            scored.append((token, None))
            continue
        scoring.save(conn, s)
        scored.append((token, s.score))
        previous = last_alert(conn, token["address"])
        ok, reason = should_alert(cfg, s.score, previous, now)
        if not ok or not telegram_ok:
            continue
        message = format_message(conn, cfg, token, s, previous)
        try:
            delivered = notify.send(message, cfg)
        except notify.TelegramNotConfigured as err:
            log.warning("Uyarı gönderilemedi: %s", err)
            telegram_ok = False
            continue
        if not delivered:
            continue  # bir sonraki turda tekrar denenir
        conn.execute("INSERT INTO alerts (token, score, sent_at, dry_run, message) VALUES (?, ?, ?, ?, ?)",
                     (token["address"], s.score, db.utc_now(), int(cfg["dry_run"]), message))
        tracking.start(conn, token, "alert", s.score)
        sent += 1
        log.info("Uyarı: %s skor %d (%s)%s", token["symbol"], s.score, reason, " [deneme modu]" if cfg["dry_run"] else "")
    controls = tracking.add_controls(conn, cfg, scored)
    conn.commit()
    log.info("Skor turu: %d uyarı, %d token karşılaştırma grubuna eklendi.", sent, controls)
    return sent


# --- "Çalışıyorum" özeti ---

def heartbeat_message(conn: sqlite3.Connection, cfg: dict) -> str:
    cutoff24 = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    seen, passed = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(passed), 0) FROM tokens WHERE first_seen_at >= ?", (cutoff24,)
    ).fetchone()
    vetoed = conn.execute(
        "SELECT COUNT(DISTINCT token) FROM risk_checks WHERE level = 'veto' AND updated_at >= ?", (cutoff24,)
    ).fetchone()[0]
    alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE sent_at >= ?", (cutoff24,)).fetchone()[0]
    return (
        "📡 <b>Memecoin Radar çalışıyor</b>\n"
        f"Son 24 saat: {seen} yeni token görüldü, {passed} tanesi filtreleri geçti, "
        f"{vetoed} tanesi riskten elendi, {alerts} uyarı gönderildi.\n"
        f"Helius bugün: ~{db.usage_today(conn, helius.SERVICE):,} kredi "
        f"(bütçe {cfg['helius_daily_credit_budget']:,})."
    )


def maybe_heartbeat(conn: sqlite3.Connection, cfg: dict) -> bool:
    hours = cfg["heartbeat_hours"]
    if hours <= 0:
        return False
    last = db.get_status(conn).get("last_heartbeat_at")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=hours):
        return False
    if last is None:
        # İlk açılışta hemen mesaj atma; saymaya şimdi başla.
        db.set_status(conn, "last_heartbeat_at", db.utc_now())
        return False
    try:
        delivered = notify.send(heartbeat_message(conn, cfg), cfg)
    except notify.TelegramNotConfigured:
        return False
    if delivered:
        db.set_status(conn, "last_heartbeat_at", db.utc_now())
    return delivered
