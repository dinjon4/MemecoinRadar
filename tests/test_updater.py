"""Güncelleme testleri: geçici bir 'GitHub' (bare repo) ve bir kurulum (clone) ile, internetsiz."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import updater


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "HOME": str(cwd)})


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.dev = root / "dev"          # geliştiricinin bilgisayarı (güncellemeyi yükleyen)
        self.friend = root / "friend"    # arkadaşın kurulumu
        git(root, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(root, "clone", "-q", str(self.remote), str(self.dev))
        (self.dev / "main.py").write_text("print(1)\n")
        (self.dev / "requirements.txt").write_text("requests\n")
        git(self.dev, "add", ".")
        git(self.dev, "commit", "-q", "-m", "ilk sürüm")
        git(self.dev, "push", "-q", "origin", "main")
        git(root, "clone", "-q", str(self.remote), str(self.friend))
        self.patch = mock.patch.object(updater, "BASE_DIR", self.friend)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def publish(self, filename, text, message):
        (self.dev / filename).write_text(text)
        git(self.dev, "add", ".")
        git(self.dev, "commit", "-q", "-m", message)
        git(self.dev, "push", "-q", "origin", "main")

    def test_up_to_date(self):
        s = updater.check()
        self.assertTrue(s.installed)
        self.assertEqual((s.behind, s.changes), (0, []))
        self.assertEqual(updater.apply(), "Zaten en güncel sürüm.")

    def test_new_version_is_detected_and_applied(self):
        self.publish("main.py", "print(2)\n", "Yeni özellik")
        s = updater.check()
        self.assertEqual((s.behind, s.changes), (1, ["Yeni özellik"]))
        with mock.patch.object(updater.subprocess, "run", wraps=subprocess.run) as run:
            summary = updater.apply()
        self.assertIn("1 yeni değişiklik", summary)
        self.assertNotIn("paket", summary)  # requirements değişmedi → pip çalışmadı
        self.assertFalse(any("pip" in c.args[0] for c in run.call_args_list))
        self.assertEqual((self.friend / "main.py").read_text(), "print(2)\n")
        self.assertEqual(updater.check().behind, 0)

    def test_requirements_change_installs_packages(self):
        self.publish("requirements.txt", "requests\nkeyring\n", "Yeni paket")
        real_run = subprocess.run
        def fake_run(cmd, **kw):
            if "pip" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real_run(cmd, **kw)
        with mock.patch.object(updater.subprocess, "run", side_effect=fake_run) as run:
            summary = updater.apply()
        self.assertIn("Yeni paketler kuruldu", summary)
        self.assertTrue(any("pip" in c.args[0] for c in run.call_args_list))

    def test_local_edits_block_update(self):
        self.publish("main.py", "print(2)\n", "Yeni")
        (self.friend / "main.py").write_text("print('elle değişti')\n")
        s = updater.check()
        self.assertEqual(s.local_changes, ["main.py"])
        with self.assertRaises(updater.UpdateError):
            updater.apply()
        self.assertEqual((self.friend / "main.py").read_text(), "print('elle değişti')\n")

    def test_untracked_personal_files_do_not_block(self):
        self.publish("main.py", "print(2)\n", "Yeni")
        (self.friend / "config.yaml").write_text("whale_min_usd: 1500\n")  # kişisel, git'te değil
        updater.apply()
        self.assertEqual((self.friend / "config.yaml").read_text(), "whale_min_usd: 1500\n")

    def test_version_and_release_notes(self):
        (self.dev / "radar").mkdir()
        (self.dev / "radar" / "__init__.py").write_text('VERSION = "1.1.0"\n')
        self.publish("CHANGELOG.md", "# Sürüm notları\n\n## v1.1.0 — 2026-10-10\n- Haber katmanı eklendi.\n- Hata düzeltmesi.\n\n"
                                     "## v1.0.0 — 2026-10-08\n- İlk sürüm.\n", "v1.1.0")
        with mock.patch.object(updater, "VERSION", "1.0.0"):
            s = updater.check()
            self.assertEqual((s.version, s.latest), ("v1.0.0", "v1.1.0"))
            self.assertEqual(s.notes, [("v1.1.0 — 2026-10-10", ["Haber katmanı eklendi.", "Hata düzeltmesi."])])
            self.assertIn("v1.1.0 indirildi", updater.apply())

    def test_parse_and_compare_versions(self):
        self.assertEqual(updater.parse_version("v1.2.10"), (1, 2, 10))
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("v1.9.3"))
        self.assertEqual(updater.parse_version("bozuk"), (0,))
        notes = updater.release_notes("## v2.0.0 — x\n- a\n## v1.0.1 — y\n- b\n## v1.0.0 — z\n- c\n", "v1.0.0")
        self.assertEqual([t for t, _ in notes], ["v2.0.0 — x", "v1.0.1 — y"])

    def test_not_a_clone(self):
        with mock.patch.object(updater, "BASE_DIR", Path(self.tmp.name)):
            s = updater.check()
        self.assertFalse(s.installed)
        self.assertIn("GitHub'dan indirilmemiş", s.message)


if __name__ == "__main__":
    unittest.main()
