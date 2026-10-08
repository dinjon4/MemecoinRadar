"""GitHub'dan güncelleme (panel → Sistem → Güncelle).

Kurulum `git clone` ile yapıldıysa çalışır. Yeni sürüm varsa:
1. `git pull --ff-only` ile indirilir (yerel kod değişikliği varsa güncelleme yapılmaz, ezilmez),
2. requirements.txt değiştiyse paketler kurulur,
3. Tarama servisi ve panel yeniden başlatılır (bkz. request_restart).

Kişisel dosyalar (config.yaml, data/, logs/, .env) git'te değildir; güncelleme onlara dokunmaz.
Anahtarlar işletim sistemi kasasındadır; güncellemeden etkilenmez.
"""

import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from radar import BASE_DIR, VERSION

log = logging.getLogger(__name__)

# Panel bu kodla kapanırsa başlatıcı onu yeniden açar.
RESTART_EXIT_CODE = 75
GIT_TIMEOUT = 60


class UpdateError(Exception):
    pass


def _git(*args: str, timeout: int = GIT_TIMEOUT) -> str:
    if not shutil.which("git"):
        raise UpdateError("git bulunamadı. Mac'te Xcode araçları, Windows'ta 'Git for Windows' kurulu olmalı.")
    try:
        out = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=timeout,
                             env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        raise UpdateError(f"git {args[0]} zaman aşımına uğradı (internet bağlantısını kontrol edin).") from None
    if out.returncode != 0:
        raise UpdateError(f"git {args[0]} başarısız: {(out.stderr or out.stdout).strip()[:300]}")
    # Sadece sondaki boşluk silinir: 'status --porcelain' satırlarının başındaki boşluk anlamlıdır.
    return out.stdout.rstrip()


@dataclass
class Status:
    installed: bool                     # git deposu ve uzak sunucu tanımlı mı
    version: str = ""                   # kurulu sürüm, ör. "v1.0.0"
    behind: int = 0                     # indirilmemiş yeni commit sayısı
    changes: list[str] = field(default_factory=list)   # yeni commit başlıkları
    local_changes: list[str] = field(default_factory=list)  # elle değiştirilmiş dosyalar
    latest: str = ""                    # GitHub'daki sürüm, ör. "v1.1.0"
    notes: list[tuple[str, list[str]]] = field(default_factory=list)  # yeni sürümlerin notları
    message: str = ""


def current_version() -> str:
    return f"v{VERSION}"


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' / '1.2.3' → (1, 2, 3); okunamazsa (0,)."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else (0,)


def remote_version(upstream: str) -> str:
    """GitHub'daki sürüm numarası (radar/__init__.py içindeki VERSION)."""
    try:
        text = _git("show", f"{upstream}:radar/__init__.py")
    except UpdateError:
        return ""
    m = re.search(r'^VERSION = "([^"]+)"', text, flags=re.MULTILINE)
    return f"v{m.group(1)}" if m else ""


def release_notes(changelog: str, newer_than: str) -> list[tuple[str, list[str]]]:
    """CHANGELOG.md'den, kurulu sürümden yeni sürümlerin notları: [(başlık, [notlar])], en yeni önce."""
    current = parse_version(newer_than)
    out = []
    for block in re.split(r"^## ", changelog, flags=re.MULTILINE)[1:]:
        title, _, body = block.partition("\n")
        if parse_version(title) > current:
            notes = [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]
            out.append((title.strip(), notes))
    return sorted(out, key=lambda item: parse_version(item[0]), reverse=True)


def check(fetch: bool = True) -> Status:
    """Yeni sürüm var mı? fetch=False ise sadece en son indirilen bilgiye bakar (internet kullanmaz)."""
    try:
        _git("rev-parse", "--is-inside-work-tree")
        upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    except UpdateError:
        return Status(False, current_version(), message="Bu kurulum GitHub'dan indirilmemiş (git clone); "
                                                        "güncelleme butonu kullanılamaz.")
    if fetch:
        _git("fetch", "--quiet", upstream.split("/", 1)[0])
    behind = int(_git("rev-list", "--count", f"HEAD..{upstream}") or 0)
    changes = _git("log", "--format=%s", f"HEAD..{upstream}").splitlines() if behind else []
    local = [line[3:] for line in _git("status", "--porcelain", "--untracked-files=no").splitlines()]
    latest, notes = current_version(), []
    if behind:
        latest = remote_version(upstream) or latest
        try:
            notes = release_notes(_git("show", f"{upstream}:CHANGELOG.md"), current_version())
        except UpdateError:
            notes = []
    return Status(True, current_version(), behind, changes, local, latest, notes)


def apply() -> str:
    """Yeni sürümü indirir; gerekirse paketleri kurar. Kullanıcıya gösterilecek özeti döner."""
    status = check(fetch=True)
    if not status.installed:
        raise UpdateError(status.message)
    if status.local_changes:
        raise UpdateError("Bu bilgisayarda program dosyaları elle değiştirilmiş; güncelleme bunları ezmemek için "
                          "yapılmadı: " + ", ".join(status.local_changes[:5]))
    if not status.behind:
        return "Zaten en güncel sürüm."
    before = _git("rev-parse", "HEAD")
    _git("pull", "--ff-only", "--quiet")
    changed = _git("diff", "--name-only", before, "HEAD").splitlines()
    summary = f"{status.latest} indirildi." if status.latest != status.version else \
        f"{status.behind} yeni değişiklik indirildi."
    if "requirements.txt" in changed:
        log.info("requirements.txt değişti, paketler kuruluyor.")
        out = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                             cwd=BASE_DIR, capture_output=True, text=True, timeout=600)
        if out.returncode != 0:
            raise UpdateError("Kod indirildi ama paketler kurulamadı: " + out.stderr.strip()[-300:])
        summary += " Yeni paketler kuruldu."
    log.info("Güncelleme: %s", summary)
    return summary
