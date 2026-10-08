"""Aşama 4 testleri: skor, bekleme süresi, mesaj biçimi, heartbeat (internet gerekmez)."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from radar import alerts, config, db, notify, scoring

SOL = "So11111111111111111111111111111111111111112"


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.cfg = config.defaults() | {"whale_min_usd": 1500}
        self.now = datetime.now(timezone.utc)
        self.add_token("MEME", "MEME", liquidity=20_000, mc=100_000)

    def tearDown(self):
        self.conn.close()

    def iso(self, hours_ago=0.0):
        return (self.now - timedelta(hours=hours_ago)).isoformat(timespec="seconds")

    def add_token(self, address, symbol, liquidity, mc, name="Meme <Coin>"):
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, pair_address, dex, "
            "url, passed, quote_mint, quote_price_usd, market_cap_usd, liquidity_usd, volume_h24_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, 'POOL', 'pumpswap', 'https://dexscreener.com/solana/pool', 1, ?, 100, ?, ?, 1000)",
            (address, symbol, name, self.iso(3), self.iso(3), self.iso(), SOL, mc, liquidity),
        )

    def token(self, address="MEME"):
        return self.conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()

    def trade(self, sig, wallet, side, usd, when="2026-10-08T10:00:00+00:00"):
        self.conn.execute("INSERT INTO trades VALUES (?, 'MEME', ?, ?, 1, 1, ?, ?)", (sig, wallet, side, usd, when))

    def check(self, key, level, title="t"):
        self.conn.execute("INSERT OR REPLACE INTO risk_checks VALUES ('MEME', ?, ?, ?, '', ?)", (key, level, title, self.iso()))


class ScoreTest(Base):
    def test_strong_token(self):
        # Net giriş $10K = likiditenin %50'si → tam akış puanı; 8 ayrı alıcı → tam çeşitlilik; liq/MC %20 → tam.
        for i in range(8):
            self.trade(f"b{i}", f"W{i}", "buy", 1_250 + 1_000, when=f"2026-10-08T10:00:0{i}+00:00")
        self.trade("s1", "X", "sell", 8_000)
        self.check("mint_authority", "ok")
        s = scoring.compute(self.conn, self.cfg, self.token())
        self.assertEqual((s.flow_points, s.buyers_points, s.liquidity_points), (50, 30, 20))
        self.assertEqual(s.score, 100)
        self.assertEqual(s.buyers, 8)

    def test_bundle_buyers_count_as_one_group(self):
        for i in range(5):
            self.trade(f"b{i}", f"W{i}", "buy", 2_000)  # hepsi aynı saniyede
        s = scoring.compute(self.conn, self.cfg, self.token())
        self.assertEqual((s.buyers, s.buyer_groups), (5, 1))
        self.assertAlmostEqual(s.buyers_points, 30 / 8, places=1)

    def test_outflow_gives_zero_flow_points(self):
        self.trade("s1", "X", "sell", 50_000)
        s = scoring.compute(self.conn, self.cfg, self.token())
        self.assertEqual(s.flow_points, 0)
        self.assertLess(s.net_usd, 0)

    def test_warnings_reduce_score_and_veto_has_no_score(self):
        self.trade("b1", "W1", "buy", 10_000)
        base = scoring.compute(self.conn, self.cfg, self.token()).score
        self.check("holders_top10", "warn", "İlk 10 %46")
        self.check("dev_sold", "warn", "Dev satışı %100")
        s = scoring.compute(self.conn, self.cfg, self.token())
        self.assertEqual(s.score, base - 16)
        self.assertCountEqual(s.warn_titles, ["İlk 10 %46", "Dev satışı %100"])
        self.check("mint_authority", "veto")
        self.assertIsNone(scoring.compute(self.conn, self.cfg, self.token()))

    def test_score_never_negative(self):
        for k in range(10):
            self.check(f"w{k}", "warn")
        self.assertEqual(scoring.compute(self.conn, self.cfg, self.token()).score, 0)

    def test_save_and_load_roundtrip(self):
        self.trade("b1", "W1", "buy", 10_000)
        s = scoring.compute(self.conn, self.cfg, self.token())
        scoring.save(self.conn, s)
        self.assertEqual(scoring.load(self.conn, "MEME"), s)


class ShouldAlertTest(unittest.TestCase):
    cfg = config.defaults()
    now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    def prev(self, score, hours_ago):
        return {"score": score, "sent_at": (self.now - timedelta(hours=hours_ago)).isoformat()}

    def test_below_threshold(self):
        self.assertFalse(alerts.should_alert(self.cfg, 59, None, self.now)[0])

    def test_first_alert(self):
        self.assertTrue(alerts.should_alert(self.cfg, 60, None, self.now)[0])

    def test_cooldown(self):
        self.assertFalse(alerts.should_alert(self.cfg, 70, self.prev(65, 2), self.now)[0])
        self.assertTrue(alerts.should_alert(self.cfg, 70, self.prev(65, 7), self.now)[0])

    def test_big_jump_skips_cooldown(self):
        ok, reason = alerts.should_alert(self.cfg, 80, self.prev(65, 1), self.now)
        self.assertTrue(ok)
        self.assertIn("65 → 80", reason)


class MessageAndRunTest(Base):
    def setUp(self):
        super().setUp()
        for i in range(8):
            self.trade(f"b{i}", f"W{i}", "buy", 2_500, when=f"2026-10-08T10:00:0{i}+00:00")
        self.check("dev_sold", "ok", "Dev satış yapmadı")
        self.check("mint_authority", "ok", "Mint yetkisi kapalı")
        self.check("holders_top10", "warn", "İlk 10 cüzdanın arzdaki payı: %46")

    def test_message_contents_and_escaping(self):
        s = scoring.compute(self.conn, self.cfg, self.token())
        msg = alerts.format_message(self.conn, self.cfg, self.token(), s)
        self.assertIn(f"<b>$MEME</b> — Skor {s.score}/100", msg)
        self.assertIn("Meme &lt;Coin&gt;", msg)           # token adı HTML olarak kaçırıldı
        self.assertIn("Whale net akış: +$20.0K (8 alıcı cüzdan)", msg)
        self.assertIn("⚠️ İlk 10 cüzdanın arzdaki payı: %46", msg)
        self.assertIn("✅ Dev satış yapmadı", msg)
        self.assertIn("x.com/search?q=MEME&amp;f=live", msg)
        self.assertIn("MC: $100.0K | Likidite: $20.0K | Yaş: 3 saat", msg)

    def test_run_sends_once_then_respects_cooldown(self):
        with mock.patch.object(notify, "send", return_value=True) as send:
            self.assertEqual(alerts.run(self.conn, self.cfg), 1)
            self.assertEqual(alerts.run(self.conn, self.cfg), 0)
        self.assertEqual(send.call_count, 1)
        row = self.conn.execute("SELECT * FROM alerts").fetchone()
        self.assertEqual(row["token"], "MEME")
        self.assertIsNotNone(scoring.load(self.conn, "MEME"))

    def test_failed_delivery_is_retried_next_round(self):
        with mock.patch.object(notify, "send", return_value=False):
            self.assertEqual(alerts.run(self.conn, self.cfg), 0)
        with mock.patch.object(notify, "send", return_value=True) as send:
            self.assertEqual(alerts.run(self.conn, self.cfg), 1)
        send.assert_called_once()

    def test_dry_run_is_recorded(self):
        cfg = self.cfg | {"dry_run": True}
        with mock.patch.object(notify, "credentials", side_effect=AssertionError("Telegram'a gidilmemeli")):
            self.assertEqual(alerts.run(self.conn, cfg), 1)
        self.assertEqual(self.conn.execute("SELECT dry_run FROM alerts").fetchone()[0], 1)

    def test_vetoed_token_score_removed(self):
        with mock.patch.object(notify, "send", return_value=True):
            alerts.run(self.conn, self.cfg)
        self.check("freeze_authority", "veto")
        with mock.patch.object(notify, "send", return_value=True) as send:
            alerts.run(self.conn, self.cfg)
        send.assert_not_called()
        self.assertIsNone(scoring.load(self.conn, "MEME"))


class HeartbeatTest(Base):
    def test_first_call_starts_clock_then_sends_when_due(self):
        with mock.patch.object(notify, "send", return_value=True) as send:
            self.assertFalse(alerts.maybe_heartbeat(self.conn, self.cfg))
            send.assert_not_called()
            db.set_status(self.conn, "last_heartbeat_at", self.iso(25))
            self.assertTrue(alerts.maybe_heartbeat(self.conn, self.cfg))
            self.assertIn("çalışıyor", send.call_args.args[0])
            self.assertFalse(alerts.maybe_heartbeat(self.conn, self.cfg))  # yeni saat başladı

    def test_disabled(self):
        db.set_status(self.conn, "last_heartbeat_at", self.iso(100))
        with mock.patch.object(notify, "send") as send:
            self.assertFalse(alerts.maybe_heartbeat(self.conn, self.cfg | {"heartbeat_hours": 0}))
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
