"""Aşama 2: cüzdan akışı.

Her token için havuzun büyük alım/satımları Helius'tan çekilir. Ücretsiz kotayı korumak için sadece
whale eşiğine yakın büyüklükteki işlemler istenir (Helius tutar filtresi); küçük işlemler hiç gelmez.

Alım/satım, havuzun bakiye değişiminden okunur:
- Havuza SOL girdi, havuzdan token çıktı → alım. Tokenı alan cüzdan = alıcı.
- Havuzdan SOL çıktı, havuza token girdi → satım. Tokenı veren cüzdan = satıcı.
Bu yöntem cüzdan USDC ile ödeme yapıp araya başka havuz girse de doğru çalışır.

Kısıt: sadece kasaları havuz adresine ait olan DEX'lerde çalışır (şimdilik PumpSwap).
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from radar import db
from radar.sources import helius

log = logging.getLogger(__name__)

# Kasaları havuz adresine ait olan, bu yöntemle akışı okunabilen DEX'ler (DexScreener adlarıyla).
SUPPORTED_DEXES = {"pumpswap"}

QUOTE_DECIMALS = {
    "So11111111111111111111111111111111111111112": 9,   # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,  # USDT
}

# Fiyat oynamasına pay: Helius'tan eşiğin bu oranı kadar büyük işlemler istenir,
# whale sayılması için ise tam eşik (whale_min_usd) kullanılır.
FETCH_MARGIN = 0.8
# Her token için bir turda en fazla bu kadar cüzdanın kalan bakiyesi sorgulanır.
BALANCE_REFRESH_LIMIT = 15


@dataclass(frozen=True)
class Trade:
    signature: str
    wallet: str
    side: str            # "buy" / "sell"
    token_amount: float
    quote_amount: float
    usd: float
    block_time: datetime


def balance_deltas(meta: dict) -> dict[tuple[str, str], float]:
    """İşlemdeki (sahip, mint) başına token bakiyesi değişimi."""
    def amounts(balances):
        out = {}
        for b in balances or []:
            amount = float(b["uiTokenAmount"].get("uiAmountString") or 0)
            out[b["accountIndex"]] = (b.get("owner", ""), b["mint"], amount)
        return out

    pre, post = amounts(meta.get("preTokenBalances")), amounts(meta.get("postTokenBalances"))
    deltas: dict[tuple[str, str], float] = {}
    for idx in pre.keys() | post.keys():
        owner, mint, _ = post.get(idx) or pre[idx]
        change = (post[idx][2] if idx in post else 0.0) - (pre[idx][2] if idx in pre else 0.0)
        if change:
            deltas[(owner, mint)] = deltas.get((owner, mint), 0.0) + change
    return deltas


def _signer(tx: dict) -> str:
    key = tx["transaction"]["message"]["accountKeys"][0]
    return key["pubkey"] if isinstance(key, dict) else key


def parse_swap(tx: dict, pool: str, mint: str, quote_mint: str, quote_price_usd: float) -> Trade | None:
    """İşlem bu havuzda bir alım/satımsa Trade, değilse (likidite ekleme, boş işlem vb.) None döner."""
    deltas = balance_deltas(tx["meta"])
    pool_quote = deltas.get((pool, quote_mint), 0.0)
    pool_token = deltas.get((pool, mint), 0.0)
    if pool_quote > 0 and pool_token < 0:
        side = "buy"
    elif pool_quote < 0 and pool_token > 0:
        side = "sell"
    else:
        return None

    # Tokenı alan (alımda) ya da veren (satımda) havuz dışındaki en büyük cüzdan.
    others = [(owner, d) for (owner, m), d in deltas.items() if m == mint and owner != pool]
    if side == "buy":
        others = [o for o in others if o[1] > 0]
        wallet = max(others, key=lambda o: o[1])[0] if others else _signer(tx)
    else:
        others = [o for o in others if o[1] < 0]
        wallet = min(others, key=lambda o: o[1])[0] if others else _signer(tx)

    quote_amount = abs(pool_quote)
    return Trade(
        signature=tx["transaction"]["signatures"][0],
        wallet=wallet,
        side=side,
        token_amount=abs(pool_token),
        quote_amount=quote_amount,
        usd=quote_amount * quote_price_usd,
        block_time=datetime.fromtimestamp(tx["blockTime"], timezone.utc),
    )


def unsupported_reason(token: sqlite3.Row) -> str | None:
    if token["dex"] not in SUPPORTED_DEXES:
        return f"{token['dex']} havuzları için akış henüz desteklenmiyor"
    if token["quote_mint"] not in QUOTE_DECIMALS:
        return "havuzun karşı tokenı tanınmıyor"
    if not token["quote_price_usd"]:
        return "karşı token fiyatı bilinmiyor"
    return None


def update_token(conn: sqlite3.Connection, cfg: dict, token: sqlite3.Row) -> int:
    """Tokenın yeni büyük işlemlerini çeker ve kaydeder. Yeni kaydedilen işlem sayısını döner."""
    reason = unsupported_reason(token)
    if reason:
        log.debug("%s atlandı: %s", token["symbol"], reason)
        return 0

    state = conn.execute("SELECT last_block_time FROM flow_state WHERE token = ?", (token["address"],)).fetchone()
    if state and state["last_block_time"]:
        since = state["last_block_time"]
    else:
        since = int(datetime.fromisoformat(token["created_at"]).timestamp())

    decimals = QUOTE_DECIMALS[token["quote_mint"]]
    min_quote = cfg["whale_min_usd"] * FETCH_MARGIN / token["quote_price_usd"]
    txs = helius.transactions_for_address(
        conn, token["pair_address"], since=since,
        transfer_mint=token["quote_mint"], min_transfer_raw=int(min_quote * 10 ** decimals),
    )

    new_trades: list[Trade] = []
    for tx in txs:
        trade = parse_swap(tx, token["pair_address"], token["address"], token["quote_mint"], token["quote_price_usd"])
        if trade is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO trades (signature, token, wallet, side, token_amount, quote_amount, usd, block_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (trade.signature, token["address"], trade.wallet, trade.side, trade.token_amount,
             trade.quote_amount, trade.usd, trade.block_time.isoformat(timespec="seconds")),
        )
        if cur.rowcount:
            new_trades.append(trade)

    if txs:
        conn.execute(
            "INSERT INTO flow_state (token, last_block_time, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET last_block_time = excluded.last_block_time, updated_at = excluded.updated_at",
            (token["address"], max(tx["blockTime"] for tx in txs), db.utc_now()),
        )
    conn.commit()

    # İşlem yapan en büyük cüzdanların kalan bakiyesini güncelle.
    wallets = sorted({t.wallet: t.usd for t in new_trades}.items(), key=lambda w: -w[1])[:BALANCE_REFRESH_LIMIT]
    for wallet, _ in wallets:
        try:
            amount = helius.token_balance(conn, wallet, token["address"])
        except helius.HeliusError as e:
            log.warning("Bakiye alınamadı (%s): %s", wallet[:8], e)
            continue
        conn.execute(
            "INSERT INTO wallet_balances (token, wallet, amount, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(token, wallet) DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at",
            (token["address"], wallet, amount, db.utc_now()),
        )
    conn.commit()

    if new_trades:
        log.info("%s: %d yeni büyük işlem.", token["symbol"], len(new_trades))
    return len(new_trades)


def tokens_to_check(conn: sqlite3.Connection, cfg: dict) -> list[sqlite3.Row]:
    """Filtreleri geçmiş, hâlâ yeni, akışı okunabilen ve risk kontrolünden veto almamış tokenlar;
    hacmi yüksekten düşüğe, en fazla flow_max_tokens."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=cfg["token_max_age_hours"])).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT * FROM tokens WHERE passed = 1 AND created_at >= ? "
        "AND address NOT IN (SELECT token FROM risk_checks WHERE level = 'veto') "
        "ORDER BY volume_h24_usd DESC", (cutoff,)
    ).fetchall()
    return [r for r in rows if unsupported_reason(r) is None][: cfg["flow_max_tokens"]]


def run(conn: sqlite3.Connection, cfg: dict) -> None:
    """Bir akış turu: seçilen tokenların hepsini günceller. Günlük kredi bütçesi dolarsa durur."""
    if not helius.is_configured():
        log.warning("Cüzdan akışı atlandı: .env dosyasında HELIUS_API_KEY yok.")
        return
    budget = cfg["helius_daily_credit_budget"]
    tokens = tokens_to_check(conn, cfg)
    total = 0
    for token in tokens:
        used = db.usage_today(conn, helius.SERVICE)
        if used >= budget:
            log.warning("Helius günlük kredi bütçesi doldu (%d/%d). Akış yarın devam edecek.", used, budget)
            break
        try:
            total += update_token(conn, cfg, token)
        except helius.HeliusError as e:
            log.warning("%s akışı alınamadı: %s", token["symbol"], e)
    log.info("Akış turu: %d token kontrol edildi, %d yeni büyük işlem. Bugünkü Helius kullanımı: ~%d kredi.",
             len(tokens), total, db.usage_today(conn, helius.SERVICE))


# --- Raporlama (terminal ve panel) ---

def wallet_table(conn: sqlite3.Connection, token: str, whale_min_usd: float) -> list[dict]:
    """Cüzdan başına özet (sadece whale büyüklüğündeki işlemler), net akışa göre sıralı."""
    rows = conn.execute(
        """
        SELECT t.wallet,
               SUM(CASE WHEN side = 'buy'  THEN usd ELSE 0 END) AS buy_usd,
               SUM(CASE WHEN side = 'sell' THEN usd ELSE 0 END) AS sell_usd,
               SUM(CASE WHEN side = 'buy'  THEN 1 ELSE 0 END)   AS buys,
               SUM(CASE WHEN side = 'sell' THEN 1 ELSE 0 END)   AS sells,
               MIN(CASE WHEN side = 'buy'  THEN block_time END) AS first_buy,
               b.amount AS remaining
        FROM trades t
        LEFT JOIN wallet_balances b ON b.token = t.token AND b.wallet = t.wallet
        WHERE t.token = ? AND t.usd >= ?
        GROUP BY t.wallet
        """,
        (token, whale_min_usd),
    ).fetchall()
    table = [
        {
            "wallet": r["wallet"], "buy_usd": r["buy_usd"], "sell_usd": r["sell_usd"],
            "net_usd": r["buy_usd"] - r["sell_usd"], "buys": r["buys"], "sells": r["sells"],
            "first_buy": r["first_buy"], "remaining": r["remaining"],
        }
        for r in rows
    ]
    return sorted(table, key=lambda w: -abs(w["net_usd"]))


def token_summary(conn: sqlite3.Connection, token: str, whale_min_usd: float) -> dict:
    """Token başına whale özeti: net akış (giriş +, çıkış −), alıcı/satıcı cüzdan sayısı."""
    r = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN side = 'buy' THEN usd ELSE -usd END), 0) AS net_usd,
               COALESCE(SUM(CASE WHEN side = 'buy' THEN usd ELSE 0 END), 0)    AS buy_usd,
               COALESCE(SUM(CASE WHEN side = 'sell' THEN usd ELSE 0 END), 0)   AS sell_usd,
               COUNT(DISTINCT CASE WHEN side = 'buy' THEN wallet END)          AS buyers,
               COUNT(DISTINCT CASE WHEN side = 'sell' THEN wallet END)         AS sellers,
               COUNT(*) AS trades
        FROM trades WHERE token = ? AND usd >= ?
        """,
        (token, whale_min_usd),
    ).fetchone()
    return dict(r)


def format_wallet_table(rows: list[dict]) -> str:
    if not rows:
        return "Bu token için whale büyüklüğünde işlem bulunamadı."
    usd = lambda v: f"${v:,.0f}"
    lines = [f"{'CÜZDAN':<12} {'ALIM':>10} {'SATIM':>10} {'NET':>11} {'İŞLEM':>7} {'İLK ALIM (UTC)':>17} {'KALAN TOKEN':>14}"]
    for w in rows:
        remaining = f"{w['remaining']:,.0f}" if w["remaining"] is not None else "—"
        first = w["first_buy"][5:16].replace("T", " ") if w["first_buy"] else "—"
        lines.append(
            f"{w['wallet'][:4]}…{w['wallet'][-4:]:<7} {usd(w['buy_usd']):>10} {usd(w['sell_usd']):>10} "
            f"{('+' if w['net_usd'] >= 0 else '-') + usd(abs(w['net_usd'])):>11} {w['buys']:>3}/{w['sells']:<3} "
            f"{first:>17} {remaining:>14}"
        )
    return "\n".join(lines)
