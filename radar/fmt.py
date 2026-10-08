"""Ortak biçimlendirme (panel ve Telegram mesajları)."""


def usd(value: float | None, signed: bool = False) -> str:
    """$85.2K, $1.25M, -$3.4K; signed=True ise artılara '+' konur."""
    if value is None:
        return "—"
    sign = ("+" if value > 0 else "-" if value < 0 else "") if signed else ("-" if value < 0 else "")
    v = abs(value)
    if v >= 1_000_000_000:
        s = f"{v / 1_000_000_000:.2f}B"
    elif v >= 1_000_000:
        s = f"{v / 1_000_000:.2f}M"
    elif v >= 1_000:
        s = f"{v / 1_000:.1f}K"
    else:
        s = f"{v:,.0f}"
    return f"{sign}${s}"


def hours(value: float | None) -> str:
    if value is None:
        return "?"
    if value < 1:
        return f"{max(1, round(value * 60))} dk"
    return f"{value:.1f} saat".replace(".0 saat", " saat")
