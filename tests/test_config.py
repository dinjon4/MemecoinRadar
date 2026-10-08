"""Ayar doğrulama testleri. Çalıştırma: python -m unittest"""

import tempfile
import unittest
from pathlib import Path

from radar import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.yaml"

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_is_created_with_defaults(self):
        cfg = config.load(self.path)
        self.assertEqual(cfg, config.defaults())
        self.assertTrue(self.path.exists())

    def test_save_and_load_roundtrip(self):
        values = config.defaults() | {"whale_min_usd": 12000, "dry_run": True}
        config.save(values, self.path)
        self.assertEqual(config.load(self.path), values)

    def test_saved_file_keeps_nested_weights(self):
        config.save(config.defaults(), self.path)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("score_weights:\n", text)
        self.assertIn("  whale_net_flow: 50", text)

    def test_out_of_range_rejected(self):
        _, errors = config.validate(config.defaults() | {"scan_interval_minutes": 0})
        self.assertEqual(len(errors), 1)

    def test_wrong_type_rejected(self):
        _, errors = config.validate(config.defaults() | {"whale_min_usd": "çok"})
        self.assertEqual(len(errors), 1)
        _, errors = config.validate(config.defaults() | {"dry_run": "evet"})
        self.assertEqual(len(errors), 1)

    def test_weights_must_sum_to_100(self):
        _, errors = config.validate(config.defaults() | {"score_weights.whale_net_flow": 60})
        self.assertTrue(any("100" in e for e in errors))

    def test_missing_key_uses_default(self):
        self.path.write_text("scan_interval_minutes: 5\n", encoding="utf-8")
        cfg = config.load(self.path)
        self.assertEqual(cfg["scan_interval_minutes"], 5)
        self.assertEqual(cfg["whale_min_usd"], config.SETTINGS_BY_KEY["whale_min_usd"].default)

    def test_invalid_file_raises(self):
        self.path.write_text("scan_interval_minutes: -3\n", encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(self.path)


if __name__ == "__main__":
    unittest.main()
