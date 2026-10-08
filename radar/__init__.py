"""Memecoin Radar — Solana memecoin izleme aracı (sadece izleme, alım-satım yok)."""

from pathlib import Path

VERSION = "0.1"
USER_AGENT = f"MemecoinRadar/{VERSION}"

# Hangi aşamadayız: panel sadece bu aşamaya kadar kullanılan ayarları gösterir.
CURRENT_STAGE = 2

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "radar.db"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "radar.log"

DISCLAIMER = "Yatırım tavsiyesi değildir."
