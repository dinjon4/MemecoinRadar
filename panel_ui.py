"""Panel görünümü: renkler, CSS ve küçük HTML parçaları (kartlar, listeler, rozetler).

Dışarıdan gelen her metin (token adları dahil) HTML'e konmadan önce esc() ile kaçırılır.
"""

import hashlib
import html

import streamlit as st

# Renkler (.streamlit/config.toml ile uyumlu)
BG = "#0a110e"
CARD = "#101b16"
CARD_2 = "#0c1511"
BORDER = "#1c2b23"
LIME = "#c5f23a"
TEXT = "#e8efe9"
MUTED = "#7f9289"
RED = "#ff6b6b"
AMBER = "#f5b942"

CSS = f"""
<style>
/* Genel */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px; }}
h1, h2, h3 {{ letter-spacing: -0.02em; }}
[data-testid="stHeader"] {{ background: transparent; }}

/* Kenar çubuğu menüsü */
[data-testid="stSidebar"] {{ border-right: 1px solid {BORDER}; }}
[data-testid="stSidebarNavLink"] {{ border-radius: 14px; padding: 0.55rem 0.9rem; margin: 2px 0; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: linear-gradient(90deg, rgba(197,242,58,0.20), rgba(197,242,58,0.04));
    box-shadow: inset 0 0 0 1px rgba(197,242,58,0.18);
}}

/* Streamlit içerikli kartlar: st.container(key="card-...") */
[class*="st-key-card"] {{
    background: linear-gradient(160deg, {CARD} 0%, {CARD_2} 100%);
    border: 1px solid {BORDER};
    border-radius: 22px;
    padding: 1.3rem 1.4rem 1.1rem;
}}
[class*="st-key-glow"] {{
    background:
        radial-gradient(ellipse at 70% 30%, rgba(197,242,58,0.13), transparent 60%),
        linear-gradient(160deg, {CARD} 0%, {CARD_2} 100%);
}}

/* Butonlar */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {{
    background: #15231c; border: 1px solid {BORDER}; color: {TEXT};
}}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseLinkButton-secondary"]:hover {{
    border-color: {LIME}; color: {LIME};
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
    color: #0a110e; font-weight: 600;
}}

/* Saf HTML parçaları */
.mr-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 14px; }}
.mr-card {{
    background: linear-gradient(160deg, {CARD} 0%, {CARD_2} 100%);
    border: 1px solid {BORDER}; border-radius: 22px; padding: 18px 20px; color: {TEXT};
}}
.mr-card h4 {{ margin: 0 0 12px; font-size: 1.05rem; font-weight: 600; color: {TEXT}; }}
.mr-kpi-label {{ color: {MUTED}; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; }}
.mr-kpi-value {{ font-size: 1.65rem; font-weight: 650; margin-top: 6px; letter-spacing: -0.02em; }}
.mr-kpi-sub {{ color: {MUTED}; font-size: 0.78rem; margin-top: 4px; }}
.mr-chip {{ font-size: 0.75rem; font-weight: 600; padding: 3px 8px; border-radius: 8px; white-space: nowrap; }}
.mr-up {{ color: {LIME}; background: rgba(197,242,58,0.12); }}
.mr-down {{ color: {RED}; background: rgba(255,107,107,0.12); }}
.mr-warn {{ color: {AMBER}; background: rgba(245,185,66,0.12); }}
.mr-muted-chip {{ color: {MUTED}; background: rgba(127,146,137,0.12); }}
.mr-pos {{ color: {LIME}; }} .mr-neg {{ color: {RED}; }} .mr-dim {{ color: {MUTED}; }}
.mr-row {{ display: flex; align-items: center; gap: 12px; padding: 11px 0; border-top: 1px solid {BORDER}; }}
.mr-row:first-of-type {{ border-top: none; }}
.mr-row .mr-main {{ flex: 1; min-width: 0; }}
.mr-row .mr-title {{ font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mr-row .mr-sub {{ color: {MUTED}; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mr-row .mr-right {{ text-align: right; white-space: nowrap; }}
.mr-avatar {{
    width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.85rem; color: #0a110e; flex-shrink: 0;
}}
.mr-empty {{ color: {MUTED}; font-size: 0.9rem; padding: 8px 0; }}
.mr-status {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 12px;
              font-size: 0.85rem; font-weight: 600; }}
.mr-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
.mr-header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
              margin-bottom: 18px; }}
.mr-header h1 {{ margin: 0; font-size: 1.9rem; }}
.mr-header .mr-sub {{ color: {MUTED}; font-size: 0.9rem; }}
.mr-check {{ display: flex; gap: 10px; padding: 9px 0; border-top: 1px solid {BORDER}; }}
.mr-check:first-of-type {{ border-top: none; }}
.mr-check .mr-title {{ font-weight: 600; font-size: 0.92rem; }}
.mr-check .mr-sub {{ color: {MUTED}; font-size: 0.8rem; margin-top: 2px; }}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


# --- Biçimlendirme ---

def usd(value: float | None, signed: bool = False) -> str:
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


def tone(value: float | None) -> str:
    if not value:
        return "mr-dim"
    return "mr-pos" if value > 0 else "mr-neg"


def chip(text: str, kind: str = "up") -> str:
    return f'<span class="mr-chip mr-{kind}">{esc(text)}</span>'


def avatar(symbol: str) -> str:
    """Sembolün ilk harfiyle renkli yuvarlak (renk sembole göre sabit)."""
    letters = (symbol or "?").lstrip("$")[:2].upper() or "?"
    hue = int(hashlib.md5((symbol or "").encode()).hexdigest()[:2], 16) * 360 // 256
    return f'<div class="mr-avatar" style="background: hsl({hue} 70% 62%)">{esc(letters)}</div>'


# --- Parçalar ---

def header(title: str, subtitle: str = "", right_html: str = "") -> None:
    st.html(f'<div class="mr-header"><div><h1>{esc(title)}</h1>'
            f'<div class="mr-sub">{esc(subtitle)}</div></div><div>{right_html}</div></div>')


def status_pill(alive: bool, text: str) -> str:
    color = LIME if alive else RED
    bg = "rgba(197,242,58,0.10)" if alive else "rgba(255,107,107,0.10)"
    return (f'<span class="mr-status" style="background:{bg}; color:{color}">'
            f'<span class="mr-dot" style="background:{color}; box-shadow: 0 0 10px {color}"></span>{esc(text)}</span>')


def kpi_grid(items: list[dict]) -> None:
    """items: {label, value, chip (html, opsiyonel), sub (opsiyonel), value_class (opsiyonel)}"""
    cards = "".join(
        f'<div class="mr-card"><div class="mr-kpi-label"><span>{esc(i["label"])}</span>{i.get("chip", "")}</div>'
        f'<div class="mr-kpi-value {i.get("value_class", "")}">{esc(i["value"])}</div>'
        + (f'<div class="mr-kpi-sub">{esc(i["sub"])}</div>' if i.get("sub") else "")
        + "</div>"
        for i in items
    )
    st.html(f'<div class="mr-grid">{cards}</div>')


def list_card(title: str, rows: list[str], empty: str = "Henüz veri yok.") -> None:
    body = "".join(rows) if rows else f'<div class="mr-empty">{esc(empty)}</div>'
    st.html(f'<div class="mr-card"><h4>{esc(title)}</h4>{body}</div>')


def list_row(left_html: str, title: str, sub: str, right_top_html: str, right_bottom_html: str = "") -> str:
    return (f'<div class="mr-row">{left_html}<div class="mr-main"><div class="mr-title">{esc(title)}</div>'
            f'<div class="mr-sub">{esc(sub)}</div></div>'
            f'<div class="mr-right"><div>{right_top_html}</div><div class="mr-sub">{right_bottom_html}</div></div></div>')


def checks_card(title: str, checks: list, icons: dict, footer: str = "") -> None:
    rows = "".join(
        f'<div class="mr-check"><div>{icons.get(c["level"], "?")}</div><div>'
        f'<div class="mr-title">{esc(c["title"])}</div>'
        + (f'<div class="mr-sub">{esc(c["detail"])}</div>' if c["detail"] else "")
        + "</div></div>"
        for c in checks
    )
    foot = f'<div class="mr-kpi-sub" style="margin-top:10px">{esc(footer)}</div>' if footer else ""
    st.html(f'<div class="mr-card"><h4>{esc(title)}</h4>{rows}{foot}</div>')
