"""Aşama 8 (Erken Hacim) testleri: kayıtlı gerçek API cevaplarıyla (internet gerekmez)."""

import copy
import json
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from radar import config, db, http
from radar.early import collect, summary
from radar.sources import QUOTE_MINTS

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
SOL = "So11111111111111111111111111111111111111112"


def load(name):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def gt_item(address="POOL1", token="MINT1", created=NOW - timedelta(minutes=30), token_is_base=True,
            m5_buys=10, m5_volume="1500.5"):
    base, quote = (token, SOL) if token_is_base else (SOL, token)
    return {
        "id": f"solana_{address}", "type": "pool",
        "attributes": {
            "address": address, "name": "MEME / SOL" if token_is_base else "SOL / MEME",
            "pool_created_at": created.isoformat().replace("+00:00", "Z"),
            "base_token_price_usd": "0.0012" if token_is_base else "150.0",
            "quote_token_price_usd": "150.0" if token_is_base else "0.0012",
            "market_cap_usd": None, "fdv_usd": "42000.5", "reserve_in_usd": "18000",
            "transactions": {
                "m5": {"buys": m5_buys, "sells": 4, "buyers": 9, "sellers": 3},
                "m15": {"buys": 20, "sells": 8, "buyers": 15, "sellers": 6},
                "h1": {"buys": 40, "sells": 20, "buyers": 30, "sellers": 12},
            },
            "volume_usd": {"m5": m5_volume, "m15": "3000", "h1": "9000"},
        },
        "relationships": {
            "base_token": {"data": {"id": f"solana_{base}", "type": "token"}},
            "quote_token": {"data": {"id": f"solana_{quote}", "type": "token"}},
            "dex": {"data": {"id": "pump-fun", "type": "dex"}},
        },
    }


def ds_pair(address="POOL1", m5_buys=7, m5_volume=2000.0, liquidity=True):
    pair = {
        "chainId": "solana", "dexId": "pumpfun", "pairAddress": address,
        "baseToken": {"address": "MINT1", "name": "Meme Coin", "symbol": "MEME"},
        "priceUsd": "0.0013", "marketCap": 45000,
        "txns": {"m5": {"buys": m5_buys, "sells": 2}, "h1": {"buys": 50, "sells": 30}},
        "volume": {"m5": m5_volume, "h1": 12000.0},
    }
    if liquidity:
        pair["liquidity"] = {"usd": 20000.0}
    return pair


def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init(conn)
    return conn


def cfg(**overrides) -> dict:
    values = config.defaults()
    values.update(early_enabled=True, **overrides)
    return values


class ParseTest(unittest.TestCase):
    def test_gt_real_response(self):
        payload = load("geckoterminal_pools.json")
        parsed = [collect.parse_gt_pool(item, collect.SOLANA) for item in payload["data"]]
        ok = [p for p in parsed if p]
        self.assertTrue(ok)
        for pool, snap in ok:
            self.assertNotIn(pool.token, QUOTE_MINTS)
            self.assertEqual(snap["source"], "gt")
            self.assertEqual(snap["pool"], pool.pool)
            self.assertIsInstance(snap["m5_buyers"], int)
            self.assertIsInstance(snap["m15_volume"], float)
        # SOL/USDC gibi iki tarafı da memecoin olmayan havuzlar atlanır.
        sol_usdc = [i for i in payload["data"] if i["attributes"]["name"] == "SOL / USDC"]
        if sol_usdc:
            self.assertIsNone(collect.parse_gt_pool(sol_usdc[0], collect.SOLANA))

    def test_gt_token_on_quote_side(self):
        pool, snap = collect.parse_gt_pool(gt_item(token_is_base=False), collect.SOLANA)
        self.assertEqual(pool.token, "MINT1")
        self.assertEqual(pool.symbol, "MEME")
        self.assertEqual(snap["price_usd"], 0.0012)

    def test_gt_values(self):
        pool, snap = collect.parse_gt_pool(gt_item(), collect.SOLANA)
        self.assertEqual(pool.dex, "pump-fun")
        self.assertEqual(pool.url, "https://dexscreener.com/solana/POOL1")
        self.assertEqual(snap["market_cap_usd"], 42000.5)  # piyasa değeri yoksa FDV
        self.assertEqual(snap["liquidity_usd"], 18000.0)
        self.assertEqual((snap["m5_buys"], snap["m5_buyers"], snap["m5_volume"]), (10, 9, 1500.5))

    def test_gt_broken_item(self):
        self.assertIsNone(collect.parse_gt_pool({"id": "x"}, collect.SOLANA))

    def test_ds_real_response(self):
        pairs = load("dexscreener_pairs.json")["pairs"]
        for pair in pairs:
            meta, snap = collect.parse_ds_pair(pair)
            self.assertEqual(snap["source"], "ds")
            self.assertTrue(meta["symbol"])
            self.assertIsNone(snap["m5_buyers"])  # DexScreener'da benzersiz alıcı yok
            self.assertIsNone(snap["m15_volume"])
            self.assertIsInstance(snap["m5_buys"], int)
        # Bonding curve (pump.fun) havuzlarında DexScreener likidite vermiyor.
        bonding = [p for p in pairs if p["dexId"] == "pumpfun"]
        self.assertTrue(bonding)
        self.assertIsNone(collect.parse_ds_pair(bonding[0])[1]["liquidity_usd"])


class RoundTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()
        self.addCleanup(self.conn.close)

    def run_round(self, gt_items, ds_pairs, now=NOW, **overrides):
        with mock.patch.object(collect, "fetch_gt_list", side_effect=[gt_items, [], []]), \
             mock.patch.object(collect, "fetch_ds_pairs", return_value=ds_pairs) as ds:
            result = collect.run_round(self.conn, cfg(**overrides), now_fn=lambda: now)
        return result, ds

    def test_first_and_second_round(self):
        result, ds = self.run_round([gt_item()], [ds_pair()])
        self.assertEqual((result.listed, result.new, result.followed, result.snapshots), (1, 1, 1, 2))
        self.assertEqual(ds.call_args[0][1], ["POOL1"])
        pool = self.conn.execute("SELECT * FROM ev_pools").fetchone()
        self.assertEqual((pool["name"], pool["symbol"], pool["source"]), ("Meme Coin", "MEME", "trend 5dk"))
        self.assertEqual(pool["last_active_at"], NOW.isoformat(timespec="seconds"))

        later = NOW + timedelta(minutes=1)
        result, _ = self.run_round([gt_item()], [ds_pair()], now=later)
        self.assertEqual(result.new, 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM ev_snapshots").fetchone()[0], 4)

    def test_old_pools_skipped(self):
        result, _ = self.run_round([gt_item(created=NOW - timedelta(hours=7))], [])
        self.assertEqual((result.listed, result.new), (0, 0))

    def test_unrequested_ds_pairs_ignored(self):
        result, _ = self.run_round([gt_item()], [ds_pair(), ds_pair(address="OTHER")])
        self.assertEqual(result.snapshots, 2)

    def test_same_pool_in_two_lists_counted_once(self):
        with mock.patch.object(collect, "fetch_gt_list", side_effect=[[gt_item()], [gt_item()], []]), \
             mock.patch.object(collect, "fetch_ds_pairs", return_value=[]):
            result = collect.run_round(self.conn, cfg(), now_fn=lambda: NOW)
        self.assertEqual((result.listed, result.snapshots), (1, 1))


class FollowTest(unittest.TestCase):
    def setUp(self):
        self.conn = memory_db()
        self.addCleanup(self.conn.close)

    def add(self, address, created_min, listed_min, active_min=None):
        iso = lambda m: (NOW - timedelta(minutes=m)).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO ev_pools (pool, chain, token, created_at, first_seen_at, last_listed_at, last_active_at) "
            "VALUES (?, 'solana', ?, ?, ?, ?, ?)",
            (address, address, iso(created_min), iso(listed_min), iso(listed_min),
             iso(active_min) if active_min is not None else None),
        )

    def test_selection_and_order(self):
        self.add("RECENT_LIST", 30, 5)
        self.add("ACTIVE", 200, 150, active_min=1)
        self.add("QUIET", 30, 20)              # 15 dk'dır listede yok, hiç işlem görmedi
        self.add("FADED", 200, 150, active_min=70)  # son işlem 1 saatten eski
        self.add("TOO_OLD", 7 * 60, 1, 1)      # 6 saatten eski
        follow = collect.pools_to_follow(self.conn, collect.SOLANA, 6, 10, NOW)
        self.assertEqual(follow, ["ACTIVE", "RECENT_LIST"])
        self.assertEqual(collect.pools_to_follow(self.conn, collect.SOLANA, 6, 1, NOW), ["ACTIVE"])

    def test_prune(self):
        self.add("OLD", 5 * 24 * 60, 5 * 24 * 60)
        self.add("NEW", 30, 5)
        for pool, minutes in (("OLD", 4 * 24 * 60), ("NEW", 1)):
            collect.save_snapshot(self.conn, {"pool": pool, "source": "ds"},
                                  (NOW - timedelta(minutes=minutes)).isoformat(timespec="seconds"))
        self.assertEqual(collect.prune(self.conn, 3, NOW), 1)
        self.assertEqual([r[0] for r in self.conn.execute("SELECT pool FROM ev_pools")], ["NEW"])


class SummaryTest(unittest.TestCase):
    def test_acceleration(self):
        self.assertEqual(summary.acceleration(3000, 1000), 3.0)
        self.assertIsNone(summary.acceleration(3000, 0))
        self.assertIsNone(summary.acceleration(None, 1000))

    def test_pools(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        pool, gt_snap = collect.parse_gt_pool(gt_item(), collect.SOLANA)
        collect.save_pool(conn, pool, "trend 5dk", (NOW - timedelta(minutes=30)).isoformat(timespec="seconds"))
        # 10–40 dk önceki ölçümler ortalaması 1000$, şimdiki 4000$ → ivme 4x.
        for minutes, volume in ((35, 800.0), (20, 1200.0), (0, 4000.0)):
            snap = collect.parse_ds_pair(ds_pair(m5_volume=volume, liquidity=False))[1]
            collect.save_snapshot(conn, snap, (NOW - timedelta(minutes=minutes)).isoformat(timespec="seconds"))
        collect.save_snapshot(conn, gt_snap, NOW.isoformat(timespec="seconds"))
        rows = summary.pools(conn, 6, NOW)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["m5_volume"], 4000.0)
        self.assertAlmostEqual(r["acceleration"], 4.0)
        self.assertEqual(r["m5_buyers"], 9)
        self.assertEqual(r["liquidity_usd"], 18000.0)  # DexScreener vermediği için GeckoTerminal'den
        counts = summary.counts(conn, 6, NOW)
        self.assertEqual((counts["pools"], counts["snapshots_total"]), (1, 4))


class SharedThrottleTest(unittest.TestCase):
    def test_slots_are_spaced(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "throttle.db"
            self.assertAlmostEqual(http.reserve_shared_slot("h", 6.0, path), 0.0, delta=0.5)
            self.assertAlmostEqual(http.reserve_shared_slot("h", 6.0, path), 6.0, delta=0.5)
            self.assertAlmostEqual(http.reserve_shared_slot("h", 6.0, path), 12.0, delta=0.5)
            self.assertAlmostEqual(http.reserve_shared_slot("other", 6.0, path), 0.0, delta=0.5)

    def test_far_future_slot_is_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "throttle.db"
            http.reserve_shared_slot("h", 1.0, path)
            with sqlite3.connect(path) as c:
                c.execute("UPDATE slots SET next_at = ?", (time.time() + 3600,))
            self.assertAlmostEqual(http.reserve_shared_slot("h", 1.0, path), 0.0, delta=0.5)

    def test_unusable_file_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(http.reserve_shared_slot("h", 1.0, Path(d)))  # klasör, dosya değil


class ConfigTest(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertFalse(config.defaults()["early_enabled"])

    def test_missing_settings_written_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.yaml"
            values = config.defaults()
            config.save(values, path)
            text = path.read_text(encoding="utf-8")
            path.write_text("\n".join(l for l in text.splitlines() if "early_enabled" not in l), encoding="utf-8")
            with self.assertLogs("radar.config", level="INFO"):
                self.assertFalse(config.load(path)["early_enabled"])
            self.assertIn("early_enabled: false", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
