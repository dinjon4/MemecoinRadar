"""Telegram'a mesaj gönderme."""

import html
import logging
import os

import requests
from dotenv import load_dotenv

from radar import DISCLAIMER, ENV_PATH, http

log = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096


class TelegramNotConfigured(Exception):
    """.env içinde Telegram bilgileri eksik."""


def credentials() -> tuple[str, str]:
    load_dotenv(ENV_PATH, override=True)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    missing = [name for name, v in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if missing:
        raise TelegramNotConfigured(f".env dosyasında eksik: {', '.join(missing)}")
    return token, chat_id


def find_chat_ids() -> list[tuple[str, str]]:
    """Bot'a son mesaj atan sohbetleri (chat_id, isim) olarak döner. Sadece bot token gerekir."""
    load_dotenv(ENV_PATH, override=True)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramNotConfigured(".env dosyasında eksik: TELEGRAM_BOT_TOKEN")
    try:
        resp = http.get(f"https://api.telegram.org/bot{token}/getUpdates")
    except requests.HTTPError as e:
        raise TelegramNotConfigured(_telegram_error(e.response)) from None
    chats = {}
    for update in resp.json().get("result", []):
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
        if chat:
            name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
            chats[str(chat["id"])] = name
    return list(chats.items())


def is_configured() -> bool:
    try:
        credentials()
        return True
    except TelegramNotConfigured:
        return False


def escape(text: str) -> str:
    """Token isimleri gibi dışarıdan gelen metinleri mesaja koymadan önce bununla kaçır."""
    return html.escape(str(text), quote=False)


def send(message_html: str, cfg: dict) -> bool:
    """Mesajı gönderir ve sonuna yatırım tavsiyesi notunu ekler.

    message_html Telegram HTML biçimindedir; dışarıdan gelen metinler escape() ile kaçırılmış olmalı.
    dry_run açıksa göndermez, sadece loga yazar. Başarılıysa True döner.
    """
    text = f"{message_html}\n\n<i>{DISCLAIMER}</i>"
    if len(text) > TELEGRAM_MAX_LENGTH:
        log.warning("Mesaj çok uzun (%d karakter), kısaltılıyor.", len(text))
        text = message_html[: TELEGRAM_MAX_LENGTH - 200] + f"\n…\n\n<i>{DISCLAIMER}</i>"

    if cfg["dry_run"]:
        log.info("[DENEME MODU] Telegram'a gönderilmedi:\n%s", text)
        return True

    token, chat_id = credentials()
    try:
        resp = http.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        )
    except requests.HTTPError as e:
        # Hata mesajındaki URL bot token içerir; loga sadece Telegram'ın açıklamasını yaz.
        log.error("Telegram mesajı gönderilemedi: %s", _telegram_error(e.response))
        return False
    except requests.RequestException as e:
        log.error("Telegram'a bağlanılamadı: %s", type(e).__name__)
        return False
    log.info("Telegram mesajı gönderildi.")
    return True


def _telegram_error(resp: requests.Response | None) -> str:
    if resp is None:
        return "bilinmeyen hata"
    try:
        desc = resp.json().get("description", "")
    except ValueError:
        desc = ""
    hints = {
        401: "Bot token hatalı.",
        400: "Chat ID hatalı olabilir.",
        403: "Bot'a henüz mesaj atmamış olabilirsiniz ya da bot engellenmiş.",
    }
    return f"HTTP {resp.status_code} {desc} {hints.get(resp.status_code, '')}".strip()
