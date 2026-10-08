"""Gizli anahtar testleri. Gerçek Anahtar Zinciri'ne dokunmaz: bellekte sahte kasa kullanılır."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from radar import keys, notify
from radar.sources import helius


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError()
        del self.store[(service, username)]


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.previous = keyring.get_keyring()
        self.vault = MemoryKeyring()
        keyring.set_keyring(self.vault)
        self.dir = tempfile.TemporaryDirectory()
        self.env = Path(self.dir.name) / ".env"
        self.env_patch = mock.patch.object(keys, "ENV_PATH", self.env)
        self.env_patch.start()
        self.osenv = mock.patch.dict("os.environ", {}, clear=False)
        self.osenv.start()
        for name in keys.NAMES:
            __import__("os").environ.pop(name, None)

    def tearDown(self):
        self.osenv.stop()
        self.env_patch.stop()
        self.dir.cleanup()
        keyring.set_keyring(self.previous)

    def write_env(self, text):
        self.env.write_text(text, encoding="utf-8")

    def test_nothing_configured(self):
        self.assertIsNone(keys.get("HELIUS_API_KEY"))
        self.assertIsNone(keys.source("HELIUS_API_KEY"))
        self.assertFalse(helius.is_configured())
        self.assertFalse(notify.is_configured())

    def test_vault_wins_over_file(self):
        self.write_env("HELIUS_API_KEY=dosyadaki\n")
        self.assertEqual((keys.get("HELIUS_API_KEY"), keys.source("HELIUS_API_KEY")), ("dosyadaki", "dosya"))
        keys.save("HELIUS_API_KEY", "  kasadaki ")
        self.assertEqual((keys.get("HELIUS_API_KEY"), keys.source("HELIUS_API_KEY")), ("kasadaki", "kasa"))
        self.assertEqual(helius.api_key(), "kasadaki")

    def test_remove(self):
        keys.save("TELEGRAM_CHAT_ID", "123")
        keys.remove("TELEGRAM_CHAT_ID")
        keys.remove("TELEGRAM_CHAT_ID")  # yoksa da hata vermez
        self.assertIsNone(keys.get("TELEGRAM_CHAT_ID"))

    def test_save_rejects_unknown_and_empty(self):
        with self.assertRaises(ValueError):
            keys.save("BASKA", "x")
        with self.assertRaises(ValueError):
            keys.save("HELIUS_API_KEY", "   ")

    def test_move_file_keys_to_vault_empties_file(self):
        self.write_env("# yorum\nTELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=965\nHELIUS_API_KEY=\nBASKA=kalsin\n")
        moved = keys.move_file_keys_to_vault()
        self.assertCountEqual(moved, ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
        self.assertEqual(keys.source("TELEGRAM_BOT_TOKEN"), "kasa")
        text = self.env.read_text(encoding="utf-8")
        self.assertNotIn("123:abc", text)
        self.assertNotIn("965", text)
        self.assertIn("TELEGRAM_BOT_TOKEN=\n", text)
        self.assertIn("# yorum", text)
        self.assertIn("BASKA=kalsin", text)
        self.assertEqual(notify.credentials(), ("123:abc", "965"))

    def test_missing_telegram_message_has_no_secret(self):
        keys.save("TELEGRAM_BOT_TOKEN", "GIZLI:123")
        with self.assertRaises(notify.TelegramNotConfigured) as ctx:
            notify.credentials()
        self.assertIn("chat ID", str(ctx.exception))
        self.assertNotIn("GIZLI", str(ctx.exception))


class CheckKeysTest(unittest.TestCase):
    def test_bad_bot_token_message_has_no_secret(self):
        import requests
        resp = requests.Response()
        resp.status_code, resp._content = 401, b'{"description":"Unauthorized"}'
        err = requests.HTTPError("401 for url: https://api.telegram.org/botGIZLI:123/getMe", response=resp)
        with mock.patch.object(notify.http, "get", side_effect=err):
            with self.assertRaises(notify.TelegramNotConfigured) as ctx:
                notify.check_bot_token("GIZLI:123")
        self.assertNotIn("GIZLI", str(ctx.exception))
        self.assertIn("Bot token hatalı", str(ctx.exception))

    def test_bad_helius_key_message_has_no_secret(self):
        import requests
        resp = requests.Response()
        resp.status_code = 401
        err = requests.HTTPError("401 for url: https://mainnet.helius-rpc.com/?api-key=GIZLI", response=resp)
        with mock.patch.object(helius.http, "post", side_effect=err):
            with self.assertRaises(helius.HeliusError) as ctx:
                helius.check_key("GIZLI")
        self.assertNotIn("GIZLI", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
