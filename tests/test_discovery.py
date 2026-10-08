"""Aşama 1 testleri: kayıtlı gerçek API cevaplarıyla (internet gerekmez)."""

import json
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from radar import config, db, discovery
from radar.sources import QUOTE_MINTS, dexscreener, geckoterminal

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def load(name):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def token(**overrides) -> dexscreener.TokenInfo:
    base = dexscreener.TokenInfo(
        mint="MINT1", name="Test", symbol="TST", created_at=NOW - timedelta(hours=3),
        pair_address="PAIR1", dex="pumpswap", url="https://dexscreener.com/solana/pair1",
        price_usd=0.001, market_cap_usd=85_000, liquidity_usd=22_000, volume_h24_usd=50_000,
        buys_h24=100, sells_h24=50,
    )
    return replace(base, **overrides)


class GeckoTerminalTest(unittest.TestCase):
    def test_parse_real_response(self):
        payload = load("geckoterminal_pools.json")
        candidates = geckoterminal.parse_pools(payload, "hacim")
        # SOL/USDC gibi iki tarafı da memecoin olmayan havuzlar atlanır.
        both_quote = sum(
            1 for p in payload["data"]
            if {p["relationships"][k]["data"]["id"].split("_", 1)[1] for k in ("base_token", "quote_token")} <= QUOTE_MINTS
        )
        self.assertGreater(both_quote, 0)
        self.assertEqual(len(candidates), len(payload["data"]) - both_quote)
        for c in candidates:
            self.assertNotIn(c.mint, QUOTE_MINTS)
            self.assertIsNotNone(c.pool_created_at.tzinfo)
            self.assertEqual(c.source, "hacim")

    def test_sol_on_base_side_uses_other_token(self):
        payload = {"data": [{
            "id": "solana_POOL",
            "attributes": {"address": "POOL", "pool_created_at": "2026-10-08T09:00:00Z"},
            "relationships": {
                "base_token": {"data": {"id": "solana_So11111111111111111111111111111111111111112"}},
                "quote_token": {"data": {"id": "solana_MEME"}},
                "dex": {"data": {"id": "raydium"}},
            },
        }]}
        [c] = geckoterminal.parse_pools(payload, "yeni")
        self.assertEqual(c.mint, "MEME")

    def test_broken_pool_is_skipped(self):
        payload = {"data": [{"id": "solana_BROKEN", "attributes": {}}]}
        self.assertEqual(geckoterminal.parse_pools(payload, "yeni"), [])


class DexScreenerTest(unittest.TestCase):
    def test_summarize_real_response(self):
        pairs = load("dexscreener_tokens.json")
        mint = pairs[0]["baseToken"]["address"]
        info = dexscreener.summarize(mint, pairs)
        self.assertEqual(info.symbol, "US")
        self.assertEqual(info.dex, "pumpswap")
        self.assertEqual(info.liquidity_usd, 0)
        self.assertEqual(info.created_at, datetime.fromtimestamp(pairs[0]["pairCreatedAt"] / 1000, timezone.utc))

    def test_all_fixture_pairs_summarize_without_error(self):
        # Bazı gerçek cevaplarda "liquidity" alanı hiç yok; çökmemeli.
        pairs = load("dexscreener_tokens.json")
        for mint in {p["baseToken"]["address"] for p in pairs}:
            self.assertIsNotNone(dexscreener.summarize(mint, pairs))

    def test_multiple_pairs_sum_liquidity_and_use_earliest_creation(self):
        mk = lambda dex, liq, created: {
            "baseToken": {"address": "M", "name": "Meme", "symbol": "MEME"}, "dexId": dex,
            "pairAddress": dex, "liquidity": {"usd": liq}, "pairCreatedAt": created,
        }
        info = dexscreener.summarize("M", [mk("pumpfun", 0, 1_000_000), mk("pumpswap", 30_000, 2_000_000)])
        self.assertEqual(info.dex, "pumpswap")
        self.assertEqual(info.liquidity_usd, 30_000)
        self.assertEqual(info.created_at, datetime.fromtimestamp(1000, timezone.utc))

    def test_unknown_token_returns_none(self):
        self.assertIsNone(dexscreener.summarize("YOK", load("dexscreener_tokens.json")))


class FilterTest(unittest.TestCase):
    cfg = config.defaults()

    def test_good_token_passes(self):
        self.assertIsNone(discovery.filter_reason(token(), self.cfg, NOW))

    def test_low_liquidity(self):
        self.assertIn("likidite", discovery.filter_reason(token(liquidity_usd=500), self.cfg, NOW))

    def test_too_old(self):
        self.assertIn("eski", discovery.filter_reason(token(created_at=NOW - timedelta(hours=30)), self.cfg, NOW))

    def test_bonding_curve_respects_setting(self):
        t = token(dex="meteoradbc")
        self.assertIn("bonding curve", discovery.filter_reason(t, self.cfg, NOW))
        self.assertIsNone(discovery.filter_reason(t, self.cfg | {"include_bonding_curve": True}, NOW))

    def test_unknown_creation_time(self):
        self.assertIsNotNone(discovery.filter_reason(token(created_at=None), self.cfg, NOW))


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.cfg = config.defaults()
        now = datetime.now(timezone.utc)
        self.good = token(mint="GOOD", created_at=now - timedelta(hours=2))
        self.poor = token(mint="POOR", created_at=now - timedelta(hours=1), liquidity_usd=100)
        cand = lambda m: geckoterminal.Candidate(m, "P" + m, now, "pumpswap", "trend 1s")
        self.candidates = [cand("GOOD"), cand("POOR")]

    def tearDown(self):
        self.conn.close()

    def run_scan(self, candidates, infos):
        with mock.patch.object(geckoterminal, "discover", return_value=candidates), \
             mock.patch.object(dexscreener, "fetch_tokens", return_value=infos) as fetch:
            result = discovery.scan(self.conn, self.cfg)
        return result, fetch.call_args.args[0]

    def test_saves_passed_and_filtered(self):
        result, _ = self.run_scan(self.candidates, {"GOOD": self.good, "POOR": self.poor})
        self.assertEqual([t.mint for t in result.passed], ["GOOD"])
        self.assertEqual(result.new, 2)
        rows = {r["address"]: r for r in self.conn.execute("SELECT * FROM tokens")}
        self.assertEqual(rows["GOOD"]["passed"], 1)
        self.assertEqual(rows["POOR"]["passed"], 0)
        self.assertIn("likidite", rows["POOR"]["filter_reason"])
        self.assertEqual(rows["GOOD"]["source"], "trend 1s")

    def test_second_scan_rechecks_known_tokens_and_keeps_first_seen(self):
        self.run_scan(self.candidates, {"GOOD": self.good, "POOR": self.poor})
        first_seen = self.conn.execute("SELECT first_seen_at FROM tokens WHERE address='POOR'").fetchone()[0]
        # İkinci taramada keşif listesinde yok, ama likiditesi artmış.
        result, asked = self.run_scan([], {"POOR": replace(self.poor, liquidity_usd=50_000), "GOOD": self.good})
        self.assertCountEqual(asked, ["GOOD", "POOR"])
        self.assertEqual(result.new, 0)
        row = self.conn.execute("SELECT * FROM tokens WHERE address='POOR'").fetchone()
        self.assertEqual(row["passed"], 1)
        self.assertEqual(row["first_seen_at"], first_seen)
        self.assertEqual(row["source"], "trend 1s")  # ilk bulunduğu kaynak korunur


if __name__ == "__main__":
    unittest.main()
