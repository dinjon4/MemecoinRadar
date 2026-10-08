"""Helius RPC: havuz işlem geçmişi ve cüzdan bakiyeleri.

Ücretsiz plan: ayda 1M kredi. Kullanılan metotların maliyeti (2026-10-08, helius.dev/docs/billing/credits):
- getTransactionsForAddress (full): 100 işlem başına 10 kredi, çağrı başına en az 10
- getTokenAccountsByOwner: 1 kredi
Her çağrının tahmini kredisi api_usage tablosuna yazılır.
"""

import logging
import math
import sqlite3

import requests

from radar import db, http, keys

log = logging.getLogger(__name__)

SERVICE = "helius"
URL = "https://mainnet.helius-rpc.com/?api-key={}"
PAGE_LIMIT = 100


class HeliusError(Exception):
    """Helius çağrısı başarısız. Mesaj API anahtarı içermez."""


class HeliusNotConfigured(HeliusError):
    """Helius API anahtarı girilmemiş."""


def api_key() -> str:
    key = keys.get("HELIUS_API_KEY")
    if not key:
        raise HeliusNotConfigured("Helius API anahtarı girilmemiş (panel → Ayarlar → Bağlantı anahtarları)")
    return key


def check_key(key: str) -> None:
    """Anahtar çalışıyorsa sessizce döner, değilse HeliusError (mesajda anahtar yok)."""
    try:
        resp = http.post(URL.format(key.strip()), json={"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []})
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        raise HeliusError(f"Helius anahtarı kabul etmedi (HTTP {status}).") from None
    except requests.RequestException as e:
        raise HeliusError(f"Helius'a bağlanılamadı ({type(e).__name__}).") from None
    if "error" in resp.json():
        raise HeliusError("Helius anahtarı kabul etmedi.")


def is_configured() -> bool:
    try:
        api_key()
        return True
    except HeliusNotConfigured:
        return False


def _rpc(method: str, params: list):
    try:
        resp = http.post(URL.format(api_key()), json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    except requests.HTTPError as e:
        # Hata mesajındaki URL API anahtarını içerir; sadece durum kodunu ve cevabı aktar.
        body = e.response.text[:200] if e.response is not None else ""
        status = e.response.status_code if e.response is not None else "?"
        raise HeliusError(f"{method}: HTTP {status} {body}") from None
    except requests.RequestException as e:
        raise HeliusError(f"{method}: bağlantı hatası ({type(e).__name__})") from None
    payload = resp.json()
    if "error" in payload:
        raise HeliusError(f"{method}: {payload['error'].get('message', payload['error'])}")
    return payload["result"]


def transactions_for_address(conn: sqlite3.Connection, address: str, *, since: int,
                             transfer_mint: str, min_transfer_raw: int, max_pages: int = 5) -> list[dict]:
    """Adresin `since` (Unix sn) anından itibaren, `transfer_mint` cinsinden en az `min_transfer_raw`
    birimlik transfer içeren başarılı işlemlerini eskiden yeniye döner.

    Havuz adresi verilirse havuz kasalarındaki büyük giriş-çıkışlar, yani büyük alım/satımlar gelir.
    En fazla max_pages sayfa okunur; kalan işlemler bir sonraki turda alınır.
    """
    options = {
        "transactionDetails": "full",
        "sortOrder": "asc",
        "limit": PAGE_LIMIT,
        "maxSupportedTransactionVersion": 1,
        "filters": {
            "blockTime": {"gte": since},
            "status": "succeeded",
            "tokenAccounts": "balanceChanged",
            "tokenTransfer": {"mint": transfer_mint, "amount": {"gte": min_transfer_raw}},
        },
    }
    txs: list[dict] = []
    for _ in range(max_pages):
        result = _rpc("getTransactionsForAddress", [address, options])
        data = result.get("data") or []
        db.add_usage(conn, SERVICE, max(10, math.ceil(len(data) / 100) * 10))
        txs.extend(data)
        token = result.get("paginationToken")
        if not token or len(data) < PAGE_LIMIT:
            break
        options["paginationToken"] = token
    return txs


def token_balance(conn: sqlite3.Connection, owner: str, mint: str) -> float:
    """Cüzdanın elindeki token miktarı (tüm token hesaplarının toplamı)."""
    result = _rpc("getTokenAccountsByOwner", [owner, {"mint": mint}, {"encoding": "jsonParsed"}])
    db.add_usage(conn, SERVICE, 1)
    total = 0.0
    for acc in result.get("value", []):
        amount = acc["account"]["data"]["parsed"]["info"]["tokenAmount"].get("uiAmount")
        total += amount or 0.0
    return total
