"""Aşama 2 testleri: alım/satım ayrıştırma ve cüzdan özetleri (internet gerekmez)."""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from radar import config, db, flows
from radar.sources import helius

FIXTURES = Path(__file__).parent / "fixtures"
SOL = "So11111111111111111111111111111111111111112"
POOL, MINT = "POOL", "MEME"


def balance(index, owner, mint, amount):
    return {"accountIndex": index, "owner": owner, "mint": mint, "uiTokenAmount": {"uiAmountString": str(amount)}}


def fake_tx(signature, pre, post, signer="SIGNER", block_time=1_791_400_000):
    return {
        "blockTime": block_time,
        "transaction": {"signatures": [signature], "message": {"accountKeys": [signer]}},
        "meta": {"preTokenBalances": pre, "postTokenBalances": post},
    }


def sell_tx(signature="SELL1", wallet="SELLER", sol=50.0, tokens=1_000_000):
    pre = [balance(1, POOL, SOL, 100), balance(2, POOL, MINT, 5_000_000), balance(3, wallet, MINT, tokens)]
    post = [balance(1, POOL, SOL, 100 - sol), balance(2, POOL, MINT, 5_000_000 + tokens), balance(3, wallet, MINT, 0)]
    return fake_tx(signature, pre, post, signer=wallet)


def buy_tx(signature="BUY1", wallet="BUYER", sol=60.0, tokens=1_200_000, block_time=1_791_400_000):
    pre = [balance(1, POOL, SOL, 100), balance(2, POOL, MINT, 5_000_000)]
    post = [balance(1, POOL, SOL, 100 + sol), balance(2, POOL, MINT, 5_000_000 - tokens), balance(3, wallet, MINT, tokens)]
    return fake_tx(signature, pre, post, signer=wallet, block_time=block_time)


class ParseSwapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURES / "helius_swaps.json", encoding="utf-8") as f:
            cls.fx = json.load(f)

    def test_real_buy_paid_with_usdc(self):
        # Cüzdan USDC ödedi; işlem önce USDC→SOL, sonra SOL→token yaptı. Havuza giren SOL'den okunur.
        t = flows.parse_swap(self.fx["buy_paid_with_usdc"], self.fx["pool"], self.fx["mint"], SOL, 115.0)
        self.assertEqual(t.side, "buy")
        self.assertEqual(t.wallet, "8k9MxERq3FbzFA9moDBFCqLK3GYQ6Ym5fsKttAtRYKUt")
        self.assertAlmostEqual(t.quote_amount, 2.5924, places=3)
        self.assertAlmostEqual(t.token_amount, 651056.9525, places=3)
        self.assertAlmostEqual(t.usd, 2.5924 * 115, delta=1)
        self.assertIsNotNone(t.block_time.tzinfo)

    def test_real_noop_arbitrage_is_ignored(self):
        self.assertIsNone(flows.parse_swap(self.fx["noop_arbitrage"], self.fx["pool"], self.fx["mint"], SOL, 115.0))

    def test_sell(self):
        t = flows.parse_swap(sell_tx(), POOL, MINT, SOL, 100.0)
        self.assertEqual((t.side, t.wallet, t.quote_amount, t.usd), ("sell", "SELLER", 50.0, 5000.0))

    def test_buy_into_new_token_account(self):
        # Alıcının token hesabı işlemden önce yoktu (preTokenBalances'ta değil).
        t = flows.parse_swap(buy_tx(), POOL, MINT, SOL, 100.0)
        self.assertEqual((t.side, t.wallet, t.token_amount), ("buy", "BUYER", 1_200_000))

    def test_liquidity_add_is_not_a_trade(self):
        pre = [balance(1, POOL, SOL, 100), balance(2, POOL, MINT, 5_000_000)]
        post = [balance(1, POOL, SOL, 150), balance(2, POOL, MINT, 7_500_000)]
        self.assertIsNone(flows.parse_swap(fake_tx("LIQ", pre, post), POOL, MINT, SOL, 100.0))

    def test_signer_used_when_receiver_unknown(self):
        pre = [balance(1, POOL, SOL, 100), balance(2, POOL, MINT, 5_000_000)]
        post = [balance(1, POOL, SOL, 160), balance(2, POOL, MINT, 3_800_000)]
        t = flows.parse_swap(fake_tx("X", pre, post, signer="SIGNER"), POOL, MINT, SOL, 100.0)
        self.assertEqual(t.wallet, "SIGNER")


class UpdateTokenTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.cfg = config.defaults() | {"whale_min_usd": 5000}
        created = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, pair_address, dex, "
            "passed, quote_mint, quote_price_usd, volume_h24_usd) VALUES (?, 'MEME', 'Meme', ?, ?, ?, ?, 'pumpswap', 1, ?, 100, 1000)",
            (MINT, created, created, created, POOL, SOL),
        )
        self.token = self.conn.execute("SELECT * FROM tokens").fetchone()

    def tearDown(self):
        self.conn.close()

    def update(self, txs, balance_amount=500.0):
        with mock.patch.object(helius, "transactions_for_address", return_value=txs) as fetch, \
             mock.patch.object(helius, "token_balance", return_value=balance_amount):
            n = flows.update_token(self.conn, self.cfg, self.token)
        return n, fetch.call_args

    def test_saves_trades_and_summarizes(self):
        n, call = self.update([buy_tx("B1", "W1", sol=60), buy_tx("B2", "W2", sol=80), sell_tx("S1", "W1", sol=55)])
        self.assertEqual(n, 3)
        # Helius'tan eşiğin %80'i (5000*0.8/100 = 40 SOL) üstü istenmeli.
        self.assertEqual(call.kwargs["min_transfer_raw"], 40 * 10 ** 9)
        s = flows.token_summary(self.conn, MINT, 5000)
        self.assertEqual((s["buyers"], s["sellers"], s["trades"]), (2, 1, 3))
        self.assertAlmostEqual(s["net_usd"], 6000 + 8000 - 5500)
        rows = {w["wallet"]: w for w in flows.wallet_table(self.conn, MINT, 5000)}
        self.assertAlmostEqual(rows["W1"]["net_usd"], 500)
        self.assertEqual(rows["W1"]["remaining"], 500.0)
        self.assertEqual(rows["W2"]["buys"], 1)

    def test_trades_below_threshold_are_not_whales(self):
        self.update([buy_tx("B1", "W1", sol=45)])  # $4.500 < $5.000
        self.assertEqual(flows.token_summary(self.conn, MINT, 5000)["trades"], 0)
        self.assertEqual(flows.token_summary(self.conn, MINT, 4000)["trades"], 1)

    def test_next_round_continues_from_last_time_without_duplicates(self):
        self.update([buy_tx("B1", block_time=1_791_400_000)])
        n, call = self.update([buy_tx("B1", block_time=1_791_400_000), buy_tx("B2", block_time=1_791_400_500)])
        self.assertEqual(call.kwargs["since"], 1_791_400_000)
        self.assertEqual(n, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 2)

    def test_unsupported_dex_is_skipped(self):
        self.conn.execute("UPDATE tokens SET dex = 'raydium'")
        token = self.conn.execute("SELECT * FROM tokens").fetchone()
        self.assertIn("desteklenmiyor", flows.unsupported_reason(token))
        with mock.patch.object(helius, "transactions_for_address") as fetch:
            self.assertEqual(flows.update_token(self.conn, self.cfg, token), 0)
        fetch.assert_not_called()

    def test_budget_stops_round(self):
        db.add_usage(self.conn, helius.SERVICE, self.cfg["helius_daily_credit_budget"])
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(flows, "update_token") as update:
            flows.run(self.conn, self.cfg)
        update.assert_not_called()


class HeliusSecretTest(unittest.TestCase):
    def test_api_key_never_in_error_message(self):
        import requests
        resp = requests.Response()
        resp.status_code, resp._content = 401, b'{"error":"invalid api key"}'
        err = requests.HTTPError("401 for url: https://mainnet.helius-rpc.com/?api-key=GIZLI123", response=resp)
        with mock.patch.object(helius, "api_key", return_value="GIZLI123"), \
             mock.patch.object(helius.http, "post", side_effect=err):
            with self.assertRaises(helius.HeliusError) as ctx:
                helius._rpc("getSlot", [])
        self.assertNotIn("GIZLI123", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
