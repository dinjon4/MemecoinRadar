"""Aşama 6 testleri: akış okuma, anahtar kelimeler, eşleştirme, mesajda hikâye (internet gerekmez)."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from radar import alerts, config, db, news, scoring

FIXTURES = Path(__file__).parent / "fixtures"

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Kanal</title>
<item><title>Mistral AI Drops &apos;Le Chonk&apos;: A Massive AI Model Named After a Cat Meme</title>
<link>https://example.com/chonk</link><pubDate>Thu, 08 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Crypto lending rises again… but have they solved the risks?</title>
<link>https://example.com/lending</link><pubDate>Thu, 08 Oct 2026 09:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>reddit</title>
<entry><title>Shark Tank judge buys a capybara</title><link href="https://reddit.com/r/x/1"/>
<updated>2026-10-08T08:00:00+00:00</updated></entry></feed>"""

EVIL = """<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<rss><channel><item><title>&lol2;</title></item></channel></rss>"""


class ParseTest(unittest.TestCase):
    def test_rss(self):
        items = news.parse_feed("Decrypt", RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Mistral AI Drops 'Le Chonk': A Massive AI Model Named After a Cat Meme")
        self.assertEqual(items[0].url, "https://example.com/chonk")
        self.assertEqual(items[0].published, datetime(2026, 10, 8, 10, tzinfo=timezone.utc))

    def test_atom(self):
        [item] = news.parse_feed("Reddit", ATOM)
        self.assertEqual((item.title, item.url), ("Shark Tank judge buys a capybara", "https://reddit.com/r/x/1"))

    def test_real_google_trends_has_related_headlines(self):
        items = news.parse_feed("Google Trends", (FIXTURES / "google_trends.xml").read_text(encoding="utf-8"))
        self.assertEqual(len(items), 10)
        first = items[0]
        self.assertEqual(first.title, "mtg warhammer 40k reprint")
        self.assertIn("Wizards of the Coast Confirms Reprints", first.text)
        self.assertEqual(first.text.split("\n")[0], first.title)

    def test_dangerous_xml_is_rejected(self):
        with self.assertRaises(Exception):
            news.parse_feed("Kötü", EVIL)


class KeywordTest(unittest.TestCase):
    def test_common_words_are_not_keywords(self):
        self.assertEqual(news.keywords("TEST", "Test"), [])
        # Tam isim de sadece yaygın kelimelerden oluşuyorsa aranmaz.
        self.assertEqual(news.keywords("HELP", "Help Me"), [])
        self.assertIn("have", news.COMMON_WORDS)

    def test_distinctive_words_and_phrases(self):
        self.assertEqual(news.keywords("SHARK", "Shark Tank"), ["shark tank", "shark"])  # önce tam isim
        self.assertEqual(news.keywords("CAPY", "Capybara With A Gun"), ["capybara with a gun", "capybara", "capy"])
        self.assertEqual(news.keywords("ANTHROPIC", "Anthropic"), ["anthropic"])

    def test_crypto_jargon_and_numbers_skipped(self):
        self.assertEqual(news.keywords("4206066", "Solana Meme Coin"), [])
        self.assertEqual(news.keywords("$PEPE", "pepe"), [])

    def test_accents_and_symbols_normalized(self):
        self.assertIn("miriam", news.keywords("MIRIAM", "Help Míriam"))
        self.assertIn("starbucks", news.keywords("STARBUCKS", "스타벅스"))


class FindTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init(self.conn)
        now = datetime.now(timezone.utc)
        self.recent = (now - timedelta(hours=2)).isoformat(timespec="seconds")
        self.old = (now - timedelta(hours=200)).isoformat(timespec="seconds")
        self.add("1", "Decrypt", "Mistral AI Drops 'Le Chonk': A Massive AI Model Named After a Cat Meme", self.recent)
        self.add("2", "Cointelegraph", "Crypto lending rises again… but have they solved the risks?", self.recent)
        self.add("3", "Google Trends", "trump august financial disclosure", self.recent,
                 "trump august financial disclosure\nTrump bought up to $25 million in Meta stock")
        self.add("4", "Decrypt", "Chonk mania from last month", self.old)

    def tearDown(self):
        self.conn.close()

    def add(self, key, source, title, published, text=None):
        self.conn.execute("INSERT INTO news VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (key, source, title, f"https://e.com/{key}", published, published, text or title))

    def test_distinctive_match(self):
        [m] = news.find(self.conn, "CHONK", "Chonk", None, 48)
        self.assertEqual((m.keyword, m.source, m.context), ("chonk", "Decrypt", ""))

    def test_common_word_does_not_match(self):
        self.assertEqual(news.find(self.conn, "HAVE", "Have A Good Day", None, 48), [])

    def test_match_inside_trend_shows_related_headline(self):
        [m] = news.find(self.conn, "META", "Meta", None, 48)
        self.assertEqual(m.title, "Trump bought up to $25 million in Meta stock")
        self.assertEqual(m.context, "trump august financial disclosure")

    def test_old_news_ignored_unless_token_is_old_too(self):
        self.assertEqual(len(news.find(self.conn, "CHONK", "Chonk", None, 48)), 1)
        token_created = (datetime.now(timezone.utc) - timedelta(hours=190)).isoformat(timespec="seconds")
        self.assertEqual(len(news.find(self.conn, "CHONK", "Chonk", token_created, 48)), 2)

    def test_update_stores_and_prunes(self):
        item = news.Item("X", "Fresh capybara news", "https://e.com/c", datetime.now(timezone.utc), "Fresh capybara news")
        with mock.patch.object(news, "fetch_all", return_value=[item, item]):
            self.assertEqual(news.update(self.conn), 1)
        titles = [r[0] for r in self.conn.execute("SELECT title FROM news")]
        self.assertIn("Fresh capybara news", titles)
        self.assertNotIn("Chonk mania from last month", titles)  # 96 saatten eski silindi


class MessageTest(FindTest):
    def test_alert_message_includes_story(self):
        iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO tokens (address, symbol, name, created_at, first_seen_at, updated_at, passed, url, "
            "market_cap_usd, liquidity_usd) VALUES ('M', 'CHONK', 'Chonk', ?, ?, ?, 1, 'https://d.com', 100000, 20000)",
            (iso, iso, iso))
        token = self.conn.execute("SELECT * FROM tokens").fetchone()
        s = scoring.Score("M", 70, 30, 20, 20, 0, 5000, 3, 3, [], [])
        msg = alerts.format_message(self.conn, config.defaults(), token, s)
        self.assertIn("📰 Hikâye: <a href=\"https://e.com/1\">Mistral AI Drops 'Le Chonk'", msg)
        self.assertIn("(Decrypt, 2 saat önce)", msg)
        off = alerts.format_message(self.conn, config.defaults() | {"news_enabled": False}, token, s)
        self.assertNotIn("Hikâye", off)


if __name__ == "__main__":
    unittest.main()
