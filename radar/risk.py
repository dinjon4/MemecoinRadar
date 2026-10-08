"""Aşama 3: risk kontrolleri.

Her kontrol bir seviye ve kısa bir Türkçe açıklama üretir:
- ok      ✅ sorun yok
- info    ℹ️ bilgi (skoru etkilemez)
- warn    ⚠️ uyarı (Aşama 4'te skoru düşürür)
- veto    ⛔ ciddi risk: token elenir, skor hesaplanmaz, cüzdan akışı da izlenmez
- unknown ❔ veri alınamadı

Kaynaklar: RugCheck (ücretsiz), kendi işlem verimiz (ücretsiz), Helius (sadece dev satışı için).
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from radar import db, flows
from radar.sources import helius, rugcheck

log = logging.getLogger(__name__)

LEVEL_ICONS = {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "veto": "⛔", "unknown": "❔"}

# Aynı saniyede aynı yönde en az bu kadar farklı cüzdan işlem yaptıysa "toplu işlem" sayılır.
BUNDLE_MIN_WALLETS = 3
# RugCheck'in bulduğu bağlantılı ağlar arzın bu yüzdesinden fazlasını tutuyorsa uyarı.
INSIDER_WARN_PCT = 5.0
# LP'nin bu yüzdesinden azı kilitli/yakılmışsa uyarı (likidite çekilebilir).
LP_LOCK_WARN_PCT = 50.0


@dataclass(frozen=True)
class Check:
    key: str
    level: str
    title: str
    detail: str


# --- RugCheck raporundan yapılan kontroller ---

def authority_checks(r: rugcheck.Report, cfg: dict) -> list[Check]:
    checks = []
    if r.mint_authority:
        level = "veto" if cfg["veto_if_mint_authority"] else "warn"
        checks.append(Check("mint_authority", level, "Mint yetkisi açık",
                            "Dev istediği kadar yeni token basabilir; fiyat bir anda çökebilir."))
    else:
        checks.append(Check("mint_authority", "ok", "Mint yetkisi kapalı", "Yeni token basılamaz."))
    if r.freeze_authority:
        level = "veto" if cfg["veto_if_freeze_authority"] else "warn"
        checks.append(Check("freeze_authority", level, "Freeze yetkisi açık",
                            "Dev tokenları dondurabilir; aldığınızı satamayabilirsiniz (honeypot)."))
    else:
        checks.append(Check("freeze_authority", "ok", "Freeze yetkisi kapalı", "Tokenlar dondurulamaz."))
    return checks


def token2022_check(r: rugcheck.Report, cfg: dict) -> Check:
    if r.permanent_delegate:
        level = "veto" if cfg["veto_if_freeze_authority"] else "warn"
        return Check("token2022", level, "Kalıcı yetkili (permanent delegate) var",
                     "Bir adres herkesin tokenını izinsiz alabilir veya yakabilir.")
    if r.transfer_fee_pct > 0:
        return Check("token2022", "warn", f"Transfer ücreti %{r.transfer_fee_pct:g}",
                     "Her alım/satımda tokenın bir kısmı kesilir.")
    return Check("token2022", "ok", "Gizli token özelliği yok", "Transfer ücreti veya kalıcı yetkili yok.")


def rugged_check(r: rugcheck.Report) -> Check:
    if r.rugged:
        return Check("rugged", "veto", "RugCheck: rug yapılmış", "RugCheck bu tokenı 'rugged' olarak işaretlemiş.")
    return Check("rugged", "ok", "RugCheck: rug işareti yok", "")


def holders_check(r: rugcheck.Report, cfg: dict) -> Check:
    """İlk 10 cüzdanın payı. Havuzlar, kilit hesapları ve yakım adresleri sayılmaz."""
    skip = r.pool_addresses | rugcheck.BURN_ADDRESSES
    top = [h for h in r.holders if h.owner not in skip][:10]
    if not top:
        return Check("holders_top10", "unknown", "İlk 10 cüzdan payı bilinmiyor", "RugCheck cüzdan listesi boş.")
    pct = sum(h.pct for h in top)
    insiders = sum(1 for h in top if h.insider)
    extra = f" Bunlardan {insiders} tanesi RugCheck'e göre insider." if insiders else ""
    if pct > cfg["top10_holder_warn_pct"]:
        return Check("holders_top10", "warn", f"İlk 10 cüzdanın arzdaki payı: %{pct:.0f}",
                     f"Eşik %{cfg['top10_holder_warn_pct']}. Birkaç cüzdan satarsa fiyat sert düşebilir.{extra}")
    return Check("holders_top10", "ok", f"İlk 10 cüzdanın arzdaki payı: %{pct:.0f}",
                 f"Havuzlar hariç. Eşik %{cfg['top10_holder_warn_pct']}.{extra}")


def lp_check(r: rugcheck.Report, pair_address: str) -> Check:
    if pair_address not in r.lp_locked_pct:
        return Check("lp_lock", "unknown", "LP kilidi bilinmiyor", "RugCheck bu havuz için LP bilgisi vermedi.")
    pct = r.lp_locked_pct[pair_address]
    if pct < LP_LOCK_WARN_PCT:
        return Check("lp_lock", "warn", f"LP kilidi düşük: %{pct:.0f}",
                     "Havuzdaki likidite sahibi tarafından çekilebilir (rug pull riski).")
    return Check("lp_lock", "ok", f"LP kilidi: %{pct:.0f} (kilitli/yakılmış)", "Likidite kolayca çekilemez.")


def insider_check(r: rugcheck.Report) -> Check:
    nets = r.insider_networks
    if not nets:
        return Check("insiders", "ok", "Bağlantılı cüzdan ağı bulunmadı", "RugCheck'in transfer analizine göre.")
    wallets = sum(int(n.get("size") or 0) for n in nets)
    holding = sum(float(n.get("currentHolding") or 0) for n in nets)
    pct = 100 * holding / r.supply if r.supply else 0.0
    level = "warn" if pct >= INSIDER_WARN_PCT else "info"
    return Check("insiders", level, f"{len(nets)} bağlantılı cüzdan ağı ({wallets} cüzdan)",
                 f"Bu ağların arzdaki payı: %{pct:.1f}. Birbirine para aktarmış cüzdanlar; "
                 "büyük ihtimalle aynı kişi veya ekip (RugCheck tahmini).")


# --- Kendi verimizden yapılan kontroller ---

def bundle_check(conn: sqlite3.Connection, token: str) -> Check:
    """Aynı saniyede aynı yönde işlem yapan cüzdan grupları (XRPN'deki toplu satış gibi)."""
    groups = conn.execute(
        """
        SELECT side, block_time, COUNT(DISTINCT wallet) AS wallets, SUM(usd) AS usd
        FROM trades WHERE token = ?
        GROUP BY side, block_time HAVING COUNT(DISTINCT wallet) >= ?
        ORDER BY usd DESC
        """,
        (token, BUNDLE_MIN_WALLETS),
    ).fetchall()
    if not groups:
        return Check("bundles", "ok", "Toplu (aynı anda) büyük işlem yok",
                     "Sadece izlenen büyük işlemlere bakılır.")
    sells = [g for g in groups if g["side"] == "sell"]
    buys = [g for g in groups if g["side"] == "buy"]
    parts = []
    if sells:
        parts.append(f"{len(sells)} toplu satış (${sum(g['usd'] for g in sells):,.0f})")
    if buys:
        parts.append(f"{len(buys)} toplu alım (${sum(g['usd'] for g in buys):,.0f})")
    biggest = groups[0]
    return Check("bundles", "warn", "Aynı saniyede işlem yapan cüzdan grupları: " + ", ".join(parts),
                 f"En büyüğü: {biggest['wallets']} cüzdan, ${biggest['usd']:,.0f} "
                 f"({'satış' if biggest['side'] == 'sell' else 'alım'}). "
                 "Birlikte hareket eden cüzdanlar büyük ihtimalle tek kişidir.")


def copycat_check(conn: sqlite3.Connection, token: sqlite3.Row) -> Check:
    older = conn.execute(
        """
        SELECT symbol, name, market_cap_usd FROM tokens
        WHERE address != ? AND created_at < ? AND (LOWER(symbol) = LOWER(?) OR LOWER(name) = LOWER(?))
        ORDER BY market_cap_usd DESC LIMIT 1
        """,
        (token["address"], token["created_at"], token["symbol"], token["name"]),
    ).fetchone()
    if older:
        mc = f"${older['market_cap_usd']:,.0f}" if older["market_cap_usd"] else "bilinmiyor"
        return Check("copycat", "warn", "Kopya olabilir",
                     f"Aynı isimde daha eski bir token var: {older['symbol']} ({older['name']}), MC {mc}.")
    return Check("copycat", "ok", "Aynı isimde daha eski token yok", "Sadece programın gördüğü tokenlar arasında.")


# --- Dev (tokenı oluşturan cüzdan) satışı ---

def dev_check(conn: sqlite3.Connection, cfg: dict, token: sqlite3.Row, r: rugcheck.Report) -> Check:
    """Dev'in bu tokendan aldığı ve elinden çıkardığı miktar (Helius, artımlı).

    Dev'in elinde token kalmadıysa ve daha önce kontrol edildiyse yeni sorgu yapılmaz (kredi tasarrufu).
    """
    if not r.creator:
        return Check("dev_sold", "unknown", "Dev cüzdanı bilinmiyor", "RugCheck tokenı oluşturan cüzdanı vermedi.")

    state = conn.execute("SELECT * FROM dev_state WHERE token = ?", (token["address"],)).fetchone()
    need_fetch = state is None or r.creator_balance > 0
    if need_fetch and helius.is_configured():
        since = state["last_block_time"] if state and state["last_block_time"] else \
            int(datetime.fromisoformat(token["created_at"]).timestamp()) - 3600
        txs = helius.transactions_for_address(conn, r.creator, since=since,
                                              transfer_mint=token["address"], min_transfer_raw=1)
        received = state["received"] if state else 0.0
        sent = state["sent"] if state else 0.0
        last = state["last_block_time"] if state else None
        for tx in txs:
            # since dahil (gte) olduğu için son okunan işlem tekrar gelebilir; onu atla.
            if last is not None and tx["blockTime"] <= last:
                continue
            delta = flows.balance_deltas(tx["meta"]).get((r.creator, token["address"]), 0.0)
            if delta > 0:
                received += delta
            else:
                sent += -delta
        times = [tx["blockTime"] for tx in txs] + ([last] if last else [])
        new_last = max(times) if times else None
        conn.execute(
            "INSERT INTO dev_state (token, creator, received, sent, last_block_time, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET creator = excluded.creator, received = excluded.received, "
            "sent = excluded.sent, last_block_time = excluded.last_block_time, updated_at = excluded.updated_at",
            (token["address"], r.creator, received, sent, new_last, db.utc_now()),
        )
        conn.commit()
        state = conn.execute("SELECT * FROM dev_state WHERE token = ?", (token["address"],)).fetchone()

    if state is None:
        return Check("dev_sold", "unknown", "Dev satışı bilinmiyor", "Helius ayarlanmamış (.env: HELIUS_API_KEY).")
    received, sent = state["received"], state["sent"]
    short = f"{r.creator[:4]}…{r.creator[-4:]}"
    if received <= 0:
        return Check("dev_sold", "ok", "Dev bu tokendan hiç almamış",
                     f"Dev cüzdanı: {short}. Elindeki: {r.creator_balance / 10 ** r.decimals:,.0f}.")
    pct = min(100.0, 100 * sent / received)
    detail = (f"Dev cüzdanı: {short}. Aldığı: {received:,.0f}, elinden çıkardığı: {sent:,.0f} "
              "(satış veya başka cüzdana aktarım).")
    if cfg["veto_if_dev_sold"] and pct > cfg["dev_sold_veto_pct"]:
        return Check("dev_sold", "veto", f"Dev satışı: %{pct:.0f} (eleme eşiği %{cfg['dev_sold_veto_pct']})", detail)
    if pct > 0:
        return Check("dev_sold", "warn", f"Dev satışı: %{pct:.0f}",
                     detail + " Dev çıktıktan sonra toplulukla devam eden tokenlar da var; çoğu ise söner.")
    return Check("dev_sold", "ok", "Dev satış yapmadı", detail)


# --- Çalıştırma ---

def check_token(conn: sqlite3.Connection, cfg: dict, token: sqlite3.Row) -> list[Check]:
    """Tek token için tüm kontrolleri yapar ve kaydeder."""
    checks: list[Check] = []
    try:
        r = rugcheck.fetch_report(token["address"])
    except rugcheck.RugCheckError as e:
        log.warning("%s: %s", token["symbol"], e)
        r = None

    if r is not None:
        checks += authority_checks(r, cfg)
        checks += [token2022_check(r, cfg), rugged_check(r), holders_check(r, cfg),
                   lp_check(r, token["pair_address"]), insider_check(r)]
        try:
            checks.append(dev_check(conn, cfg, token, r))
        except helius.HeliusError as e:
            log.warning("%s dev kontrolü yapılamadı: %s", token["symbol"], e)
            checks.append(Check("dev_sold", "unknown", "Dev satışı kontrol edilemedi", str(e)[:200]))
    else:
        checks.append(Check("rugcheck", "unknown", "RugCheck raporu alınamadı",
                            "Mint/freeze, holder ve dev kontrolleri bir sonraki turda tekrar denenecek."))

    checks += [bundle_check(conn, token["address"]), copycat_check(conn, token)]

    now = db.utc_now()
    if r is not None:
        conn.execute("DELETE FROM risk_checks WHERE token = ? AND check_key = 'rugcheck'", (token["address"],))
    for c in checks:
        conn.execute(
            "INSERT INTO risk_checks (token, check_key, level, title, detail, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(token, check_key) DO UPDATE SET level = excluded.level, title = excluded.title, "
            "detail = excluded.detail, updated_at = excluded.updated_at",
            (token["address"], c.key, c.level, c.title, c.detail, now),
        )
    conn.commit()
    return checks


def tokens_to_check(conn: sqlite3.Connection, cfg: dict) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=cfg["token_max_age_hours"])).isoformat(timespec="seconds")
    return conn.execute(
        "SELECT * FROM tokens WHERE passed = 1 AND created_at >= ? ORDER BY volume_h24_usd DESC LIMIT ?",
        (cutoff, cfg["flow_max_tokens"]),
    ).fetchall()


def run(conn: sqlite3.Connection, cfg: dict) -> None:
    tokens = tokens_to_check(conn, cfg)
    vetoed = 0
    for token in tokens:
        if db.usage_today(conn, helius.SERVICE) >= cfg["helius_daily_credit_budget"]:
            log.warning("Helius günlük bütçesi doldu; risk kontrolü dev satışı olmadan devam edemez, tur durdu.")
            break
        checks = check_token(conn, cfg, token)
        vetoes = [c.title for c in checks if c.level == "veto"]
        if vetoes:
            vetoed += 1
            log.info("%s elendi (veto): %s", token["symbol"], "; ".join(vetoes))
    log.info("Risk turu: %d token kontrol edildi, %d tanesi veto aldı.", len(tokens), vetoed)


def checks_for(conn: sqlite3.Connection, token: str) -> list[sqlite3.Row]:
    order = {"veto": 0, "warn": 1, "unknown": 2, "info": 3, "ok": 4}
    rows = conn.execute("SELECT * FROM risk_checks WHERE token = ?", (token,)).fetchall()
    return sorted(rows, key=lambda r: order.get(r["level"], 9))


def vetoed_tokens(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT token FROM risk_checks WHERE level = 'veto'")}


def format_checks(rows) -> str:
    if not rows:
        return "Henüz risk kontrolü yapılmadı."
    return "\n".join(f"{LEVEL_ICONS.get(r['level'], '?')} {r['title']}" + (f"\n     {r['detail']}" if r["detail"] else "")
                     for r in rows)
