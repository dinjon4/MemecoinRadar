"""Panel özet sorguları testleri."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from radar import db, stats

SOL = "So11111111111111111111111111111111111111112"


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.now = datetime.now(timezone.utc)
        self.add_token("A", "AAA", passed=1)
        self.add_token("B", "BBB", passed=1)
        self.add_token("C", "CCC", passed=0)
        self.add_trade("t1", "A", "buy", 10_000, hours_ago=1)
        self.add_trade("t2", "A", "sell", 3_000, hours_ago=1)
        self.add_trade("t3", "B", "sell", 20_000, hours_ago=3)
        self.add_trade("t4", "B", "buy", 500, hours_ago=3)        # eşiğin altında
        self.add_trade("t5", "A", "buy", 9_000, hours_ago=30)     # 24 saatten eski

    def tearDown(self):
        self.conn.close()

    def iso(self, hours_ago):
        return (self.now - timedelta(hours=hours_ago)).isoformat(timespec="seconds")

    def add_token(self, address, symbol, passed):
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, passed, market_cap_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 100000)",
            (address, symbol, symbol, self.iso(5), self.iso(5), self.iso(0), passed),
        )

    def add_trade(self, sig, token, side, usd, hours_ago):
        self.conn.execute("INSERT INTO trades VALUES (?, ?, 'W', ?, 1, 1, ?, ?)", (sig, token, side, usd, self.iso(hours_ago)))

    def test_overview(self):
        self.conn.execute("INSERT INTO risk_checks VALUES ('B', 'mint_authority', 'veto', 'x', '', ?)", (self.iso(0),))
        o = stats.overview(self.conn, 24, 1500)
        self.assertEqual((o["seen"], o["passed"], o["vetoed"]), (3, 2, 1))
        self.assertEqual(o["trades"], 3)
        self.assertAlmostEqual(o["net_usd"], 10_000 - 3_000 - 20_000)

    def test_hourly_flow_has_every_hour_and_sums(self):
        points = stats.hourly_flow(self.conn, 1500, hours=24)
        self.assertEqual(len(points), 24)
        self.assertAlmostEqual(sum(p["net"] for p in points), -13_000)
        self.assertTrue(all(points[i]["hour"] < points[i + 1]["hour"] for i in range(23)))

    def test_top_flows_sorted_by_absolute_net(self):
        top = stats.top_flows(self.conn, 24, 1500)
        self.assertEqual([t["symbol"] for t in top], ["BBB", "AAA"])
        self.assertAlmostEqual(top[0]["net"], -20_000)

    def test_recent_trades_newest_first_and_above_threshold(self):
        trades = stats.recent_trades(self.conn, 1500, limit=10)
        self.assertCountEqual([t["usd"] for t in trades], [10_000, 3_000, 20_000, 9_000])  # 500 eşiğin altında
        times = [t["block_time"] for t in trades]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_recent_risks_veto_first(self):
        self.conn.execute("INSERT INTO risk_checks VALUES ('A', 'copycat', 'warn', 'kopya', '', ?)", (self.iso(0),))
        self.conn.execute("INSERT INTO risk_checks VALUES ('B', 'mint_authority', 'veto', 'mint', '', ?)", (self.iso(1),))
        self.conn.execute("INSERT INTO risk_checks VALUES ('B', 'lp_lock', 'ok', 'lp', '', ?)", (self.iso(0),))
        risks = stats.recent_risks(self.conn, 24)
        self.assertEqual([r["level"] for r in risks], ["veto", "warn"])


if __name__ == "__main__":
    unittest.main()
