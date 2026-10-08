"""DexScreener: token başına fiyat, piyasa değeri, likidite ve yaş.

Bir istekte 30 token sorgulanabiliyor ve limit geniş; bu yüzden takip edilen tüm tokenlar
her taramada buradan güncellenir.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from radar import http

log = logging.getLogger(__name__)

TOKENS_URL = "https://api.dexscreener.com/tokens/v1/solana/{}"
BATCH_SIZE = 30


@dataclass
class TokenInfo:
    mint: str
    name: str
    symbol: str
    created_at: datetime | None  # tokenın en eski havuzunun açılış zamanı
    pair_address: str            # en yüksek likiditeli havuz
    dex: str
    url: str
    price_usd: float | None
    market_cap_usd: float | None
    liquidity_usd: float         # tüm havuzların toplamı
    volume_h24_usd: float
    buys_h24: int
    sells_h24: int
    quote_mint: str = ""                  # ana havuzun karşı tokenı (genelde SOL)
    quote_price_usd: float | None = None  # karşı tokenın dolar fiyatı (ör. SOL/USD)


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize(mint: str, pairs: list[dict]) -> TokenInfo | None:
    """Bir tokenın tüm havuzlarını tek bir özete çevirir. Havuz yoksa None."""
    pairs = [p for p in pairs if p.get("baseToken", {}).get("address") == mint]
    if not pairs:
        return None
    liq = lambda p: _float((p.get("liquidity") or {}).get("usd")) or 0.0
    main = max(pairs, key=liq)
    created_ms = [p["pairCreatedAt"] for p in pairs if p.get("pairCreatedAt")]
    h24 = lambda p, k: ((p.get("txns") or {}).get("h24") or {}).get(k) or 0
    # Fiyatın USD ve karşı token cinsinden oranı, karşı tokenın (ör. SOL) dolar fiyatını verir.
    price_usd, price_native = _float(main.get("priceUsd")), _float(main.get("priceNative"))
    quote_price = price_usd / price_native if price_usd and price_native else None
    return TokenInfo(
        mint=mint,
        name=main["baseToken"].get("name") or "",
        symbol=main["baseToken"].get("symbol") or "",
        created_at=datetime.fromtimestamp(min(created_ms) / 1000, timezone.utc) if created_ms else None,
        pair_address=main.get("pairAddress", ""),
        dex=main.get("dexId", ""),
        url=main.get("url", ""),
        price_usd=price_usd,
        market_cap_usd=_float(main.get("marketCap")) or _float(main.get("fdv")),
        liquidity_usd=sum(liq(p) for p in pairs),
        volume_h24_usd=sum(_float((p.get("volume") or {}).get("h24")) or 0.0 for p in pairs),
        buys_h24=sum(h24(p, "buys") for p in pairs),
        sells_h24=sum(h24(p, "sells") for p in pairs),
        quote_mint=(main.get("quoteToken") or {}).get("address", ""),
        quote_price_usd=quote_price,
    )


def fetch_tokens(mints: list[str]) -> dict[str, TokenInfo]:
    """Tokenların özetini döner. DexScreener'da bulunamayan tokenlar sonuçta yer almaz."""
    by_mint: dict[str, list[dict]] = {m: [] for m in mints}
    for i in range(0, len(mints), BATCH_SIZE):
        batch = mints[i:i + BATCH_SIZE]
        try:
            pairs = http.get(TOKENS_URL.format(",".join(batch))).json()
        except (requests.RequestException, ValueError) as e:
            log.warning("DexScreener'dan %d token alınamadı: %s", len(batch), type(e).__name__)
            continue
        for p in pairs if isinstance(pairs, list) else []:
            mint = (p.get("baseToken") or {}).get("address")
            if mint in by_mint:
                by_mint[mint].append(p)
    result = {}
    for mint, pairs in by_mint.items():
        info = summarize(mint, pairs)
        if info:
            result[mint] = info
    return result
