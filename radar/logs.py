"""Loglama: terminale ve logs/radar.log dosyasına yazar."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from radar import LOG_DIR, LOG_PATH

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup(to_file: bool = True, level: int = logging.INFO) -> None:
    """Loglamayı kurar.

    Log dosyasına sadece tarama servisi yazar (to_file=True). Panel de yazarsa
    Windows'ta dosya döndürme (rotation) sırasında dosya kilitlenme sorunu çıkar.
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(FORMAT, "%H:%M:%S"))
    root.addHandler(console)

    if to_file:
        LOG_DIR.mkdir(exist_ok=True)
        # 1 MB dolunca yeni dosyaya geçer, en fazla 5 eski dosya tutar.
        file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(file_handler)

    # Kütüphanelerin ayrıntılı loglarını kıs.
    for noisy in ("urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def tail(lines: int = 50) -> list[str]:
    """Log dosyasının son satırlarını döner (panel için)."""
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-lines:]
