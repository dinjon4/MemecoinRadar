"""Gizli anahtarlar (Telegram bot token, chat ID, Helius API anahtarı).

Asıl yer: işletim sisteminin şifreli kasası (Mac: Anahtar Zinciri, Windows: Kimlik Bilgisi Yöneticisi).
Anahtarlar panelden girilir ve hiçbir proje dosyasında durmaz.
Yedek: kasada yoksa .env dosyası veya ortam değişkeni okunur (eski kurulumlar ve kasası olmayan sunucular için).

Değerler hiçbir zaman loga, ekrana veya hata mesajına yazılmaz.
"""

import logging
import os
import re

import keyring
from dotenv import dotenv_values

from radar import ENV_PATH

log = logging.getLogger(__name__)

SERVICE = "MemecoinRadar"

# (ad, paneldeki etiket, açıklama)
KEYS = [
    ("TELEGRAM_BOT_TOKEN", "Telegram bot token", "BotFather'ın verdiği, 123456789:ABC... biçimindeki anahtar"),
    ("TELEGRAM_CHAT_ID", "Telegram chat ID", "Mesajların gideceği sohbetin numarası"),
    ("HELIUS_API_KEY", "Helius API anahtarı", "dashboard.helius.dev → API Keys"),
]
NAMES = [k[0] for k in KEYS]


def _from_vault(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name) or None
    except keyring.errors.KeyringError as e:
        log.warning("Kasa okunamadı (%s): %s", name, type(e).__name__)
        return None


def _from_file(name: str) -> str | None:
    value = os.getenv(name) or (dotenv_values(ENV_PATH).get(name) if ENV_PATH.exists() else None)
    return value.strip() if value and value.strip() else None


def get(name: str) -> str | None:
    """Anahtarın değeri; önce kasa, yoksa .env / ortam değişkeni."""
    return _from_vault(name) or _from_file(name)


def source(name: str) -> str | None:
    """'kasa', 'dosya' veya None (hiç yok). Panel sadece bunu gösterir, değeri asla."""
    if _from_vault(name):
        return "kasa"
    if _from_file(name):
        return "dosya"
    return None


def vault_available() -> bool:
    try:
        return keyring.get_keyring().priority > 0
    except Exception:
        return False


def save(name: str, value: str) -> None:
    if name not in NAMES:
        raise ValueError(f"Bilinmeyen anahtar: {name}")
    value = value.strip()
    if not value:
        raise ValueError("Boş değer kaydedilemez.")
    keyring.set_password(SERVICE, name, value)


def remove(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def move_file_keys_to_vault() -> list[str]:
    """.env'deki dolu anahtarları kasaya taşır ve .env'deki değerlerini boşaltır.

    Sadece kasaya yazılıp geri okunabildiği doğrulanan anahtarlar .env'den silinir.
    Taşınanların adlarını döner.
    """
    if not ENV_PATH.exists():
        return []
    file_values = dotenv_values(ENV_PATH)
    moved = []
    for name in NAMES:
        value = (file_values.get(name) or "").strip()
        if not value:
            continue
        keyring.set_password(SERVICE, name, value)
        if keyring.get_password(SERVICE, name) == value:
            moved.append(name)
    if moved:
        text = ENV_PATH.read_text(encoding="utf-8")
        for name in moved:
            text = re.sub(rf"^{name}=.*$", f"{name}=", text, flags=re.MULTILINE)
        ENV_PATH.write_text(text, encoding="utf-8")
    return moved
