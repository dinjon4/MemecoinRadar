"""RugCheck: token güvenlik raporu (ücretsiz, anahtar gerektirmez, dakikada 15 istek).

Mint/freeze yetkileri, tokenı oluşturan cüzdan, en büyük cüzdanlar, LP kilidi ve
RugCheck'in kendi bulduğu bağlantılı cüzdan ağları (insider networks) buradan alınır.
"""

import logging
from dataclasses import dataclass, field

import requests

from radar import http

log = logging.getLogger(__name__)

REPORT_URL = "https://api.rugcheck.xyz/v1/tokens/{}/report"

# Arzdan sayılmaması gereken adresler (yakılmış tokenlar).
BURN_ADDRESSES = {"1nc1nerator11111111111111111111111111111111", "11111111111111111111111111111111"}


@dataclass
class Holder:
    owner: str
    pct: float          # arzın yüzdesi
    insider: bool


@dataclass
class Report:
    mint_authority: str | None
    freeze_authority: str | None
    creator: str | None
    creator_balance: float        # ham birim (decimals uygulanmamış)
    decimals: int
    supply: float                 # ham birim
    rugged: bool
    holders: list[Holder]
    pool_addresses: set[str]      # havuz/kilit hesapları (holder hesabından çıkarılır)
    lp_locked_pct: dict[str, float]  # havuz adresi → LP kilit yüzdesi
    insider_networks: list[dict]
    transfer_fee_pct: float
    permanent_delegate: str | None
    risks: list[dict] = field(default_factory=list)


class RugCheckError(Exception):
    pass


def parse_report(d: dict) -> Report:
    token = d.get("token") or {}
    markets = d.get("markets") or []
    pools = {m["pubkey"] for m in markets if m.get("pubkey")}
    # RugCheck'in tanıdığı AMM/kilit hesapları ve kilit sahipleri de havuz sayılır.
    pools |= {addr for addr, info in (d.get("knownAccounts") or {}).items()
              if (info or {}).get("type") in ("AMM", "LOCKER")}
    pools |= set((d.get("lockerOwners") or {}).keys())

    ext = d.get("token_extensions") or {}
    fee = d.get("transferFee") or {}
    return Report(
        mint_authority=token.get("mintAuthority", d.get("mintAuthority")),
        freeze_authority=token.get("freezeAuthority", d.get("freezeAuthority")),
        creator=d.get("creator"),
        creator_balance=float(d.get("creatorBalance") or 0),
        decimals=int(token.get("decimals") or 0),
        supply=float(token.get("supply") or 0),
        rugged=bool(d.get("rugged")),
        holders=[Holder(h.get("owner") or h.get("address", ""), float(h.get("pct") or 0), bool(h.get("insider")))
                 for h in d.get("topHolders") or []],
        pool_addresses=pools,
        lp_locked_pct={m["pubkey"]: float(((m.get("lp") or {}).get("lpLockedPct")) or 0)
                       for m in markets if m.get("pubkey")},
        insider_networks=d.get("insiderNetworks") or [],
        transfer_fee_pct=float(fee.get("pct") or 0),
        permanent_delegate=ext.get("permanentDelegate") or None,
        risks=d.get("risks") or [],
    )


def fetch_report(mint: str) -> Report:
    try:
        payload = http.get(REPORT_URL.format(mint)).json()
    except (requests.RequestException, ValueError) as e:
        raise RugCheckError(f"RugCheck raporu alınamadı: {type(e).__name__}") from None
    return parse_report(payload)
