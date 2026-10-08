"""Aşama 3 testleri: risk kontrolleri (gerçek RugCheck raporuyla, internet gerekmez)."""

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from radar import config, db, risk
from radar.sources import helius, rugcheck

FIXTURES = Path(__file__).parent / "fixtures"
SOL = "So11111111111111111111111111111111111111112"


def raw_report():
    with open(FIXTURES / "rugcheck_report.json", encoding="utf-8") as f:
        return json.load(f)


def report(**changes) -> rugcheck.Report:
    d = copy.deepcopy(raw_report())
    for key, value in changes.items():
        d[key] = value
    return rugcheck.parse_report(d)


class RugCheckParseTest(unittest.TestCase):
    def test_real_report(self):
        r = rugcheck.parse_report(raw_report())
        self.assertIsNone(r.mint_authority)
        self.assertIsNone(r.freeze_authority)
        self.assertEqual(r.creator, "BFtnjgkbiVnihLoPY87x7hCiEBenCD6zJCHtpdacZw5A")
        self.assertIn("65GHmCbyRME3XwKjTqDB7pMJw2gvj2LZryfWKczoAqFR", r.pool_addresses)
        self.assertEqual(r.lp_locked_pct["65GHmCbyRME3XwKjTqDB7pMJw2gvj2LZryfWKczoAqFR"], 100)
        self.assertEqual(len(r.insider_networks), 2)


class ReportChecksTest(unittest.TestCase):
    cfg = config.defaults()

    def level(self, check):
        return check.level

    def test_clean_token_authorities_ok(self):
        self.assertEqual([c.level for c in risk.authority_checks(report(), self.cfg)], ["ok", "ok"])

    def test_open_mint_authority_is_veto(self):
        d = raw_report()
        d["token"]["mintAuthority"] = "SomeDevWallet111"
        checks = {c.key: c.level for c in risk.authority_checks(rugcheck.parse_report(d), self.cfg)}
        self.assertEqual(checks["mint_authority"], "veto")
        cfg = self.cfg | {"veto_if_mint_authority": False}
        checks = {c.key: c.level for c in risk.authority_checks(rugcheck.parse_report(d), cfg)}
        self.assertEqual(checks["mint_authority"], "warn")

    def test_open_freeze_authority_is_veto(self):
        d = raw_report()
        d["token"]["freezeAuthority"] = "SomeDevWallet111"
        checks = {c.key: c.level for c in risk.authority_checks(rugcheck.parse_report(d), self.cfg)}
        self.assertEqual(checks["freeze_authority"], "veto")

    def test_holders_exclude_pools(self):
        r = report()
        c = risk.holders_check(r, self.cfg)
        self.assertEqual(c.level, "ok")
        # Havuz (%8,8) ve ikinci havuz (Meteora, %2,7) sayılmadan ilk 10.
        non_pool = [h.pct for h in r.holders if h.owner not in r.pool_addresses][:10]
        self.assertIn(f"%{sum(non_pool):.0f}", c.title)
        self.assertLess(sum(non_pool), sum(h.pct for h in r.holders[:10]))

    def test_holders_warn_above_threshold(self):
        c = risk.holders_check(report(), self.cfg | {"top10_holder_warn_pct": 5})
        self.assertEqual(c.level, "warn")

    def test_lp_lock(self):
        r = report()
        self.assertEqual(risk.lp_check(r, "65GHmCbyRME3XwKjTqDB7pMJw2gvj2LZryfWKczoAqFR").level, "ok")
        self.assertEqual(risk.lp_check(r, "UNKNOWN_POOL").level, "unknown")
        r.lp_locked_pct["P"] = 10
        self.assertEqual(risk.lp_check(r, "P").level, "warn")

    def test_insider_networks(self):
        c = risk.insider_check(report())
        self.assertIn("2 bağlantılı cüzdan ağı (10 cüzdan)", c.title)
        self.assertEqual(c.level, "info")  # arzın ~%2,7'si < %5
        self.assertEqual(risk.insider_check(report(insiderNetworks=[])).level, "ok")

    def test_rugged_and_token2022(self):
        self.assertEqual(risk.rugged_check(report(rugged=True)).level, "veto")
        d = raw_report()
        d["token_extensions"]["permanentDelegate"] = "Thief111"
        self.assertEqual(risk.token2022_check(rugcheck.parse_report(d), self.cfg).level, "veto")
        d = raw_report()
        d["transferFee"]["pct"] = 5
        self.assertEqual(risk.token2022_check(rugcheck.parse_report(d), self.cfg).level, "warn")


class DbChecksTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        self.cfg = config.defaults()
        now = datetime.now(timezone.utc)
        self.add_token("MEME", "SharkTank", "Shark Tank", now - timedelta(hours=1), 78_000)

    def tearDown(self):
        self.conn.close()

    def add_token(self, address, symbol, name, created, mc):
        iso = created.isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, pair_address, dex, "
            "passed, quote_mint, quote_price_usd, market_cap_usd, volume_h24_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, 'POOL', 'pumpswap', 1, ?, 100, ?, 1000)",
            (address, symbol, name, iso, iso, iso, SOL, mc),
        )

    def token(self, address="MEME"):
        return self.conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()

    def add_trade(self, sig, wallet, side, usd, when="2026-10-08T05:50:13+00:00"):
        self.conn.execute(
            "INSERT INTO trades VALUES (?, 'MEME', ?, ?, 1000, 1, ?, ?)", (sig, wallet, side, usd, when))

    def test_copycat(self):
        self.assertEqual(risk.copycat_check(self.conn, self.token()).level, "ok")
        self.add_token("ORIG", "SharkTank", "Shark Tank", datetime.now(timezone.utc) - timedelta(hours=10), 431_000)
        c = risk.copycat_check(self.conn, self.token())
        self.assertEqual(c.level, "warn")
        self.assertIn("$431,000", c.detail)
        # Eski olan, yenisinin kopyası sayılmaz.
        self.assertEqual(risk.copycat_check(self.conn, self.token("ORIG")).level, "ok")

    def test_bundle_same_second_sells(self):
        for i in range(6):
            self.add_trade(f"S{i}", f"W{i}", "sell", 10_000 * (i + 1))
        self.add_trade("B1", "X", "buy", 5_000)
        c = risk.bundle_check(self.conn, "MEME")
        self.assertEqual(c.level, "warn")
        self.assertIn("1 toplu satış ($210,000)", c.title)
        self.assertIn("6 cüzdan", c.detail)

    def test_two_wallets_same_second_is_not_bundle(self):
        self.add_trade("S1", "W1", "sell", 10_000)
        self.add_trade("S2", "W2", "sell", 10_000)
        self.assertEqual(risk.bundle_check(self.conn, "MEME").level, "ok")

    def dev_tx(self, creator, before, after, t):
        return {"blockTime": t, "meta": {
            "preTokenBalances": [{"accountIndex": 1, "owner": creator, "mint": "MEME", "uiTokenAmount": {"uiAmountString": str(before)}}],
            "postTokenBalances": [{"accountIndex": 1, "owner": creator, "mint": "MEME", "uiTokenAmount": {"uiAmountString": str(after)}}],
        }}

    def test_dev_sold_veto_and_incremental(self):
        r = report(creator="DEV", creatorBalance=1000)
        txs = [self.dev_tx("DEV", 0, 1_000_000, 100), self.dev_tx("DEV", 1_000_000, 300_000, 200)]
        cfg = self.cfg | {"veto_if_dev_sold": True}
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(helius, "transactions_for_address", return_value=txs) as fetch:
            c = risk.dev_check(self.conn, cfg, self.token(), r)
        self.assertEqual(c.level, "veto")  # %70 > %50
        self.assertIn("%70", c.title)
        # İkinci tur: son okunan zamandan devam eder, aynı işlemi iki kez saymaz.
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(helius, "transactions_for_address", return_value=[txs[1]]) as fetch:
            c = risk.dev_check(self.conn, cfg, self.token(), r)
        self.assertEqual(fetch.call_args.kwargs["since"], 200)
        self.assertIn("%70", c.title)

    def test_dev_sold_is_only_warning_by_default(self):
        r = report(creator="DEV", creatorBalance=0)
        txs = [self.dev_tx("DEV", 0, 1_000_000, 100), self.dev_tx("DEV", 1_000_000, 0, 200)]
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(helius, "transactions_for_address", return_value=txs):
            c = risk.dev_check(self.conn, self.cfg, self.token(), r)
        self.assertEqual(c.level, "warn")
        self.assertIn("%100", c.title)

    def test_dev_with_zero_balance_is_not_refetched(self):
        r = report(creator="DEV", creatorBalance=0)
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(helius, "transactions_for_address", return_value=[self.dev_tx("DEV", 0, 50, 100)]) as fetch:
            risk.dev_check(self.conn, self.cfg, self.token(), r)
            risk.dev_check(self.conn, self.cfg, self.token(), r)
        self.assertEqual(fetch.call_count, 1)

    def test_dev_never_bought(self):
        r = report(creator="DEV", creatorBalance=0)
        with mock.patch.object(helius, "is_configured", return_value=True), \
             mock.patch.object(helius, "transactions_for_address", return_value=[]):
            self.assertEqual(risk.dev_check(self.conn, self.cfg, self.token(), r).level, "ok")

    def test_check_token_saves_and_veto_excludes_from_flows(self):
        from radar import flows
        d = raw_report()
        d["token"]["mintAuthority"] = "DEV"
        with mock.patch.object(rugcheck, "fetch_report", return_value=rugcheck.parse_report(d)), \
             mock.patch.object(helius, "is_configured", return_value=False):
            risk.check_token(self.conn, self.cfg, self.token())
        levels = {r["check_key"]: r["level"] for r in risk.checks_for(self.conn, "MEME")}
        self.assertEqual(levels["mint_authority"], "veto")
        self.assertEqual(levels["dev_sold"], "unknown")
        self.assertIn("MEME", risk.vetoed_tokens(self.conn))
        self.assertEqual(flows.tokens_to_check(self.conn, self.cfg), [])

    def test_rugcheck_failure_is_unknown_not_crash(self):
        with mock.patch.object(rugcheck, "fetch_report", side_effect=rugcheck.RugCheckError("x")):
            checks = risk.check_token(self.conn, self.cfg, self.token())
        self.assertEqual({c.key for c in checks}, {"rugcheck", "bundles", "copycat"})


if __name__ == "__main__":
    unittest.main()
