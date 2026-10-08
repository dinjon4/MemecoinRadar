"""Dış veri kaynakları (API istemcileri)."""

# Memecoin olmayan, havuzlarda karşı taraf olarak kullanılan tokenlar.
QUOTE_MINTS = {
    "So11111111111111111111111111111111111111112",   # SOL (wrapped)
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

# Bonding curve (henüz gerçek havuza geçmemiş) aşamasındaki tokenların DEX kimlikleri.
# GeckoTerminal ve DexScreener farklı adlar kullanıyor; ikisi de burada.
BONDING_CURVE_DEXES = {
    "pump-fun", "pumpfun",
    "meteora-dbc", "meteoradbc",
    "bags",  # bags.fm launchpad'i (Meteora DBC üzerinde)
    "raydium-launchlab", "launchlab",
    "moonshot", "boop",
}
