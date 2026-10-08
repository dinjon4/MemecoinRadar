"""Aşama 5 testleri: gruplar, 1/6/24 saat ölçümleri, sonuçlar, haftalık özet (internet gerekmez)."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from radar import alerts, config, db, notify, tracking
from radar.sources import dexscreener

SOL = "So11111111111111111111111111111111111111112"


def info(mint, mc, liq, price=0.001):
    return dexscreener.TokenInfo(mint=mint, name="x", symbol="X", created_at=None, pair_address="P", dex="pumpswap",
                                 url="", price_usd=price, market_cap_usd=mc, liquidity_usd=liq,
                                 volume_h24_usd=0, buys_h24=0, sells_h24=0)


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.cfg = config.defaults()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.conn.close()

    def add_token(self, address, mc=100_000, liq=20_000):
        iso = self.now.isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, passed, pair_address, "
            "dex, quote_mint, quote_price_usd, price_usd, market_cap_usd, liquidity_usd, volume_h24_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 'P', 'pumpswap', ?, 100, 0.001, ?, ?, 1000)",
            (address, address, address, iso, iso, iso, SOL, mc, liq),
        )
        return self.conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()

    def backdate(self, token, hours):
        self.conn.execute("UPDATE tracking SET started_at = ? WHERE token = ?",
                          ((self.now - timedelta(hours=hours)).isoformat(timespec="seconds"), token))


class CohortTest(Base):
    def test_start_once_per_cohort(self):
        t = self.add_token("A")
        self.assertTrue(tracking.start(self.conn, t, "alert", 80))
        self.assertFalse(tracking.start(self.conn, t, "alert", 85))
        self.assertTrue(tracking.start(self.conn, t, "low", 40))
        row = self.conn.execute("SELECT * FROM tracking WHERE cohort = 'alert'").fetchone()
        self.assertEqual((row["score"], row["mc_0"], row["liq_0"]), (80, 100_000, 20_000))

    def test_sample_is_stable_and_roughly_right_size(self):
        addresses = [f"addr{i}" for i in range(2000)]
        picked = [a for a in addresses if tracking.in_sample(a, 30)]
        self.assertTrue(500 < len(picked) < 700)
        self.assertEqual(picked, [a for a in addresses if tracking.in_sample(a, 30)])
        self.assertFalse(any(tracking.in_sample(a, 0) for a in addresses))

    def test_add_controls_skips_alert_level_scores(self):
        tokens = [self.add_token(f"T{i}") for i in range(40)]
        scored = [(t, 90) for t in tokens[:10]] + [(t, 30) for t in tokens[10:30]] + [(t, None) for t in tokens[30:]]
        tracking.add_controls(self.conn, self.cfg | {"control_sample_pct": 100}, scored)
        counts = dict(self.conn.execute("SELECT cohort, COUNT(*) FROM tracking GROUP BY cohort").fetchall())
        self.assertEqual(counts, {"low": 20, "veto": 10})


class CheckpointTest(Base):
    def test_due_checkpoints_filled_in_order(self):
        t = self.add_token("A")
        tracking.start(self.conn, t, "alert", 80)
        self.backdate("A", 7)  # 1 ve 6 saat dolmuş, 24 dolmamış
        with mock.patch.object(dexscreener, "fetch_tokens", return_value={"A": info("A", 250_000, 40_000)}) as fetch:
            self.assertEqual(tracking.update(self.conn), 2)
            self.assertEqual(tracking.update(self.conn), 0)  # aynı ölçüm tekrar yapılmaz
        fetch.assert_called_once()
        row = self.conn.execute("SELECT * FROM tracking").fetchone()
        self.assertEqual((row["mc_1h"], row["mc_6h"], row["mc_24h"]), (250_000, 250_000, None))
        self.assertEqual(row["done"], 0)
        self.backdate("A", 25)
        with mock.patch.object(dexscreener, "fetch_tokens", return_value={"A": info("A", 30_000, 5_000)}):
            tracking.update(self.conn)
        row = self.conn.execute("SELECT * FROM tracking").fetchone()
        self.assertEqual((row["mc_24h"], row["done"]), (30_000, 1))

    def test_token_gone_from_dexscreener_counts_as_rugged(self):
        tracking.start(self.conn, self.add_token("A"), "alert", 80)
        self.backdate("A", 25)
        with mock.patch.object(dexscreener, "fetch_tokens", return_value={}):
            tracking.update(self.conn)
        row = self.conn.execute("SELECT * FROM tracking").fetchone()
        self.assertEqual(tracking.outcome(row, self.cfg), "crash")


class OutcomeTest(Base):
    def row(self, mc_0, mc_24, liq_24=20_000, checked=True):
        return {"mc_0": mc_0, "mc_24h": mc_24, "liq_24h": liq_24, "price_0": None, "price_24h": None,
                "checked_24h": "x" if checked else None}

    def test_outcomes(self):
        self.assertEqual(tracking.outcome(self.row(100, 150), self.cfg), "up")
        self.assertEqual(tracking.outcome(self.row(100, 149), self.cfg), "flat")
        self.assertEqual(tracking.outcome(self.row(100, 30), self.cfg), "crash")
        self.assertEqual(tracking.outcome(self.row(100, 200, liq_24=500), self.cfg), "crash")  # havuz boşaltılmış
        self.assertIsNone(tracking.outcome(self.row(100, 200, checked=False), self.cfg))

    def test_cohort_stats_and_buckets(self):
        for i, (cohort, score, mc24) in enumerate([("alert", 85, 300_000), ("alert", 72, 20_000), ("alert", 65, 120_000),
                                                   ("low", 30, 100_000), ("low", 20, 10_000)]):
            t = self.add_token(f"T{i}")
            tracking.start(self.conn, t, cohort, score)
            self.conn.execute("UPDATE tracking SET mc_24h = ?, liq_24h = 20000, checked_24h = 'x', done = 1 "
                              "WHERE token = ?", (mc24, f"T{i}"))
        s = tracking.cohort_stats(self.conn, self.cfg)
        self.assertEqual((s["alert"].finished, s["alert"].up, s["alert"].crash, s["alert"].flat), (3, 1, 1, 1))
        self.assertAlmostEqual(s["alert"].median_change, 20.0)
        self.assertEqual((s["low"].up, s["low"].crash), (0, 1))
        buckets = {b["label"]: b for b in tracking.score_buckets(self.conn, self.cfg)}
        self.assertEqual((buckets["80–100"]["n"], buckets["80–100"]["up"]), (1, 1))
        self.assertEqual(buckets["0–39"]["n"], 2)


class AlertIntegrationTest(Base):
    def test_alert_adds_token_to_alert_cohort(self):
        t = self.add_token("MEME", mc=100_000, liq=20_000)
        for i in range(8):
            self.conn.execute("INSERT INTO trades VALUES (?, 'MEME', ?, 'buy', 1, 1, 2500, ?)",
                              (f"b{i}", f"W{i}", f"2026-10-08T10:00:0{i}+00:00"))
        self.conn.execute("INSERT INTO risk_checks VALUES ('MEME', 'mint_authority', 'ok', 'ok', '', ?)",
                          (self.now.isoformat(),))
        with mock.patch.object(notify, "send", return_value=True):
            self.assertEqual(alerts.run(self.conn, self.cfg | {"whale_min_usd": 1500}), 1)
        self.assertEqual(self.conn.execute("SELECT cohort FROM tracking").fetchone()[0], "alert")


class WeeklyTest(Base):
    def at(self, y, mo, d, h, mi=0):
        return datetime(y, mo, d, h, mi, tzinfo=tracking.TZ).astimezone(timezone.utc)

    def test_due_on_configured_day_and_hour(self):
        cfg = self.cfg  # Pazartesi 10:00
        monday_9 = self.at(2026, 10, 12, 9)      # 12 Ekim 2026 Pazartesi
        monday_11 = self.at(2026, 10, 12, 11)
        sent_last_week = self.at(2026, 10, 5, 10, 5).isoformat()
        self.assertFalse(tracking.is_weekly_due(cfg, sent_last_week, monday_9))
        self.assertTrue(tracking.is_weekly_due(cfg, sent_last_week, monday_11))
        self.assertFalse(tracking.is_weekly_due(cfg, monday_11.isoformat(), self.at(2026, 10, 14, 12)))
        self.assertTrue(tracking.is_weekly_due(cfg, None, monday_11))

    def test_message_compares_cohorts(self):
        for i in range(12):
            cohort = "alert" if i < 6 else "low"
            t = self.add_token(f"T{i}")
            tracking.start(self.conn, t, cohort, 80 if cohort == "alert" else 30)
            mc24 = 300_000 if (cohort == "alert" and i < 4) else 90_000
            self.conn.execute("UPDATE tracking SET mc_24h = ?, liq_24h = 20000, checked_24h = 'x', done = 1 "
                              "WHERE token = ?", (mc24, f"T{i}"))
        msg = tracking.weekly_message(self.conn, self.cfg)
        self.assertIn("Uyarı verilenler</b> (6 token): 🟢 %67 yükseldi", msg)
        self.assertIn("daha iyi", msg)

    def test_disabled(self):
        with mock.patch.object(notify, "send") as send:
            self.assertFalse(tracking.maybe_weekly(self.conn, self.cfg | {"weekly_summary_enabled": False}))
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
