"""Memecoin Radar yerel paneli. Sadece bu bilgisayardan açılır (127.0.0.1).

Çalıştırma:  streamlit run panel.py
Görünüm (renkler, kartlar) panel_ui.py ve .streamlit/config.toml içinde.
"""

import html
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import panel_ui as ui
from radar import CURRENT_STAGE, VERSION, config, db, flows, keys, logs, notify, risk, scoring, stats
from radar.sources import helius

TZ = ZoneInfo("Europe/Istanbul")
# Tarama servisi bekleme sırasında 30 sn'de bir sinyal yazar; bundan uzun sessizlik = durmuş.
ALIVE_SECONDS = 90
# Ek parametreler (info=0, trades=0 vb.) denendi: grafik "Loading pair..." ekranında takılıyordu.
DEXSCREENER_EMBED = "https://dexscreener.com/solana/{pair}?embed=1&theme=dark"
LOGO = Path(__file__).parent / "static" / "logo.svg"

logs.setup(to_file=False)
st.set_page_config(page_title="Memecoin Radar", page_icon="📡", layout="wide")


# --- Yardımcılar ---

def local_time(iso: str | None, fmt: str = "%d.%m.%Y %H:%M:%S") -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).astimezone(TZ).strftime(fmt)


def ago(iso: str | None) -> str:
    if not iso:
        return ""
    seconds = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())
    if seconds < 60:
        return f"{seconds} sn önce"
    if seconds < 3600:
        return f"{seconds // 60} dk önce"
    return f"{seconds // 3600} sa {seconds % 3600 // 60} dk önce"


def age_hours(iso: str | None) -> float | None:
    if not iso:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600


def is_alive(status: dict) -> bool:
    hb = status.get("heartbeat_at")
    if not hb or status.get("stopped_at"):
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(hb) < timedelta(seconds=ALIVE_SECONDS)


def load_config_or_none() -> dict | None:
    try:
        return config.load()
    except config.ConfigError as e:
        st.error(str(e))
        return None


def x_search_url(query: str) -> str:
    """X (Twitter) aramasına giden link; 'live' = en yeni gönderiler."""
    return f"https://x.com/search?q={quote(query)}&f=live"


def risk_badge(vetoes: int, warns: int) -> str:
    if vetoes:
        return "⛔ elendi"
    if warns:
        return f"⚠️ {warns} uyarı"
    return "✅ temiz"


def short_wallet(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}"


def service_pill(status: dict) -> str:
    if is_alive(status):
        return ui.status_pill(True, f"Tarama çalışıyor · son tarama {ago(status.get('last_scan_at')) or '—'}")
    return ui.status_pill(False, "Tarama servisi çalışmıyor")


# --- Genel Bakış ---

def flow_chart(points: list[dict]):
    """Son 24 saatin birikimli whale net akışı: parlayan limon yeşili çizgi + gradyan dolgu."""
    total = 0.0
    data = []
    for p in points:
        total += p["net"]
        data.append({"saat": p["hour"].astimezone(TZ).replace(tzinfo=None), "birikimli": total,
                     "saatlik": p["net"], "alım": p["buys"], "satım": p["sells"]})
    base = alt.Chart(pd.DataFrame(data)).encode(
        x=alt.X("saat:T", axis=alt.Axis(format="%H:%M", title=None, grid=False, labelColor=ui.MUTED,
                                        domain=False, ticks=False, labelPadding=8)),
    )
    y = alt.Y("birikimli:Q", axis=alt.Axis(title=None, labelColor=ui.MUTED, gridColor=ui.BORDER, gridDash=[3, 4],
                                           domain=False, ticks=False, format="$~s", labelPadding=8))
    area = base.mark_area(
        line=False, interpolate="monotone",
        color=alt.Gradient(gradient="linear", x1=1, x2=1, y1=1, y2=0, stops=[
            alt.GradientStop(color="rgba(197,242,58,0)", offset=0),
            alt.GradientStop(color="rgba(197,242,58,0.35)", offset=1),
        ]),
    ).encode(y=y)
    glow = base.mark_line(interpolate="monotone", color=ui.LIME, strokeWidth=8, opacity=0.15).encode(y=y)
    line = base.mark_line(interpolate="monotone", color=ui.LIME, strokeWidth=2.5).encode(
        y=y,
        tooltip=[alt.Tooltip("saat:T", title="Saat", format="%d.%m %H:00"),
                 alt.Tooltip("birikimli:Q", title="Birikimli net", format="$,.0f"),
                 alt.Tooltip("saatlik:Q", title="Bu saat net", format="$,.0f"),
                 alt.Tooltip("alım:Q", title="Alım", format="$,.0f"),
                 alt.Tooltip("satım:Q", title="Satım", format="$,.0f")],
    )
    points_layer = base.mark_circle(color=ui.LIME, size=60, opacity=0).encode(y=y)  # tooltip için yakalama alanı
    zero = alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color=ui.MUTED, strokeDash=[4, 4], opacity=0.5).encode(y="z:Q")
    return (area + glow + zero + line + points_layer).properties(height=320).configure_view(strokeWidth=0) \
        .configure(background="transparent")


def page_overview() -> None:
    cfg = load_config_or_none() or config.defaults()
    whale_min, max_age = cfg["whale_min_usd"], cfg["token_max_age_hours"]
    conn = db.connect()
    status = db.get_status(conn)
    o = stats.overview(conn, max_age, whale_min)
    hourly = stats.hourly_flow(conn, whale_min)
    top = stats.top_flows(conn, max_age, whale_min)
    trades = stats.recent_trades(conn, whale_min)
    risks = stats.recent_risks(conn, max_age)
    credits_today = db.usage_today(conn, helius.SERVICE)
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    alerts_24h = conn.execute("SELECT COUNT(*) FROM alerts WHERE sent_at >= ?", (day_ago,)).fetchone()[0]
    conn.close()

    ui.header("Genel Bakış", f"Son {max_age} saat · whale eşiği {ui.usd(whale_min)}", service_pill(status))

    budget = cfg["helius_daily_credit_budget"]
    net = o["net_usd"]
    ui.kpi_grid([
        {"label": "İzlenen token", "value": f"{o['passed']}",
         "sub": f"{o['seen']} token görüldü, {o['seen'] - o['passed']} tanesi filtrede elendi"},
        {"label": "Whale net akış (24s)", "value": ui.usd(net, signed=True), "value_class": ui.tone(net),
         "chip": ui.chip("↑ giriş" if net > 0 else "↓ çıkış" if net < 0 else "—",
                         "up" if net > 0 else "down" if net < 0 else "muted-chip"),
         "sub": f"Alım {ui.usd(o['buy_usd'])} · Satım {ui.usd(o['sell_usd'])} · {o['trades']} işlem"},
        {"label": "Uyarı (24 saat)", "value": f"{alerts_24h}",
         "chip": ui.chip("🧪 deneme", "warn") if cfg["dry_run"] else "",
         "sub": f"Skor {cfg['min_score_to_alert']}+ · {o['vetoed']} token riskten elendi"},
        {"label": "Helius kredisi (bugün)", "value": f"{credits_today:,}",
         "chip": ui.chip(f"%{100 * credits_today / budget:.0f}", "warn" if credits_today > 0.8 * budget else "up"),
         "sub": f"Günlük bütçe {budget:,}"},
    ])

    left, right = st.columns([2.1, 1], gap="medium")
    with left.container(key="card-glow-flow"):
        st.markdown("#### Whale akışı")
        st.caption("Son 24 saatte izlenen tokenlara giren (+) ve çıkan (−) büyük paranın birikimli toplamı")
        st.altair_chart(flow_chart(hourly), width="stretch")
    with right:
        rows = [
            ui.list_row(ui.avatar(t["symbol"]), t["symbol"], f"MC {ui.usd(t['market_cap_usd'])} · Lik. {ui.usd(t['liquidity_usd'])}",
                        f'<span class="{ui.tone(t["net"])}">{ui.usd(t["net"], signed=True)}</span>',
                        f'{t["trades"]} işlem')
            for t in top
        ]
        ui.list_card("Öne çıkanlar", rows, "Henüz whale işlemi yok.")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        rows = [
            ui.list_row(ui.avatar(t["symbol"]), t["symbol"],
                        f'{local_time(t["block_time"], "%H:%M")} · cüzdan {short_wallet(t["wallet"])}',
                        f'<span class="{"mr-pos" if t["side"] == "buy" else "mr-neg"}">'
                        f'{"+" if t["side"] == "buy" else "-"}{ui.usd(t["usd"])}</span>',
                        "alım" if t["side"] == "buy" else "satım")
            for t in trades
        ]
        ui.list_card("Son büyük işlemler", rows, "Henüz whale işlemi yok.")
    with c2:
        rows = [
            ui.list_row(ui.avatar(r["symbol"]), r["symbol"], r["title"],
                        ui.chip("⛔ elendi" if r["level"] == "veto" else "⚠️ uyarı",
                                "down" if r["level"] == "veto" else "warn"),
                        ago(r["updated_at"]))
            for r in risks
        ]
        ui.list_card("Risk uyarıları", rows, "Henüz risk uyarısı yok.")


# --- Tokenlar ---

def page_tokens() -> None:
    cfg = load_config_or_none() or config.defaults()
    max_age, whale_min = cfg["token_max_age_hours"], cfg["whale_min_usd"]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age)).isoformat(timespec="seconds")
    conn = db.connect()
    rows = conn.execute("SELECT * FROM tokens WHERE created_at >= ? ORDER BY created_at DESC", (cutoff,)).fetchall()
    whale_net = {
        r["token"]: (r["net"], r["n"])
        for r in conn.execute(
            "SELECT token, SUM(CASE WHEN side = 'buy' THEN usd ELSE -usd END) AS net, COUNT(*) AS n "
            "FROM trades WHERE usd >= ? GROUP BY token", (whale_min,)
        )
    }
    risk_summary = {
        r["token"]: risk_badge(r["vetoes"], r["warns"])
        for r in conn.execute(
            "SELECT token, SUM(level = 'veto') AS vetoes, SUM(level = 'warn') AS warns FROM risk_checks GROUP BY token"
        )
    }
    scores = {r["token"]: r["score"] for r in conn.execute("SELECT token, score FROM scores")}
    passed_count = sum(r["passed"] for r in rows)
    ui.header("Tokenlar", f"Son {max_age} saatte {len(rows)} token görüldü · {passed_count} tanesi filtreleri geçti")

    with st.container(key="card-tokens"):
        c1, c2 = st.columns([2, 1])
        query = c1.text_input("Ara", placeholder="Sembol, isim veya adres (ör. BONK)",
                              label_visibility="collapsed").strip().lower()
        show_filtered = c2.toggle("Elenenleri de göster", value=False)

        now = datetime.now(timezone.utc)
        table = []
        for r in rows:
            if not show_filtered and not r["passed"]:
                continue
            if query and query not in f"{r['symbol']} {r['name']} {r['address']}".lower():
                continue
            table.append({
                "Durum": "✅" if r["passed"] else "⛔",
                "Skor": scores.get(r["address"]),
                "Risk": risk_summary.get(r["address"], "—"),
                "Sembol": r["symbol"],
                "İsim": r["name"],
                "Yaş (saat)": round((now - datetime.fromisoformat(r["created_at"])).total_seconds() / 3600, 1),
                "MC ($)": r["market_cap_usd"],
                "Likidite ($)": r["liquidity_usd"],
                "Hacim 24s ($)": r["volume_h24_usd"],
                "Alım/Satım 24s": f"{r['buys_h24']} / {r['sells_h24']}",
                "Whale net ($)": whale_net.get(r["address"], (None, 0))[0],
                "Whale işlem": whale_net.get(r["address"], (None, 0))[1],
                "DEX": r["dex"],
                "Eleme sebebi": r["filter_reason"] or "",
                "Bulunduğu liste": r["source"] or "",
                "İlk görülme": local_time(r["first_seen_at"]),
                "Link": r["url"],
                "𝕏": x_search_url(r["address"]),
                "Adres": r["address"],
            })

        if not table:
            st.info("Gösterilecek token yok. Tarama servisi çalışıyor mu? (Sistem sayfası)")
            conn.close()
            return

        st.caption("Ayrıntı için bir satırın solundaki kutuyu seçin.")
        money = st.column_config.NumberColumn(format="compact")
        event = st.dataframe(
            table, hide_index=True, width="stretch", height=min(420, 40 + 35 * len(table)),
            on_select="rerun", selection_mode="single-row",
            column_order=[c for c in table[0] if show_filtered or c != "Eleme sebebi"],
            column_config={
                "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d",
                                                         help="0–100. Uyarı eşiği Ayarlar'da."),
                "MC ($)": money, "Likidite ($)": money, "Hacim 24s ($)": money, "Whale net ($)": money,
                "Link": st.column_config.LinkColumn(display_text="DexScreener"),
                "𝕏": st.column_config.LinkColumn(display_text="ara", help="Kontrat adresiyle X'te en yeni gönderiler"),
            },
        )
    if event.selection.rows:
        token_detail(conn, table[event.selection.rows[0]]["Adres"], whale_min)
    conn.close()


def token_detail(conn, address: str, whale_min: int) -> None:
    token = conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()
    checks = risk.checks_for(conn, address)
    vetoes = sum(c["level"] == "veto" for c in checks)
    warns = sum(c["level"] == "warn" for c in checks)
    summary = flows.token_summary(conn, address, whale_min)
    age = age_hours(token["created_at"])

    st.write("")
    risk_chip = (ui.chip("⛔ elendi", "down") if vetoes else ui.chip(f"⚠️ {warns} uyarı", "warn") if warns
                 else ui.chip("✅ temiz", "up") if checks else ui.chip("risk kontrolü bekleniyor", "muted-chip"))
    st.html(
        f'<div class="mr-card" style="display:flex; align-items:center; gap:16px; flex-wrap:wrap">'
        f'{ui.avatar(token["symbol"])}<div style="flex:1; min-width:200px">'
        f'<div style="font-size:1.5rem; font-weight:700">{ui.esc(token["symbol"])} '
        f'<span class="mr-dim" style="font-size:1rem; font-weight:500">{ui.esc(token["name"])}</span></div>'
        f'<div class="mr-kpi-sub" style="font-family: ui-monospace, monospace">{ui.esc(address)}</div></div>'
        f'<div style="display:flex; gap:8px; flex-wrap:wrap">{risk_chip}{ui.chip(token["dex"] or "?", "muted-chip")}'
        f'{ui.chip(f"{age:.1f} saatlik" if age is not None else "yaş ?", "muted-chip")}</div></div>'
    )
    ui.kpi_grid([
        {"label": "Piyasa değeri", "value": ui.usd(token["market_cap_usd"])},
        {"label": "Likidite", "value": ui.usd(token["liquidity_usd"])},
        {"label": "Hacim (24s)", "value": ui.usd(token["volume_h24_usd"]),
         "sub": f"{token['buys_h24']} alım / {token['sells_h24']} satım"},
        {"label": "Whale net akış", "value": ui.usd(summary["net_usd"], signed=True) if summary["trades"] else "—",
         "value_class": ui.tone(summary["net_usd"]),
         "sub": f"{summary['buyers']} alıcı / {summary['sellers']} satıcı cüzdan"},
    ])

    c1, c2, c3 = st.columns(3)
    c1.link_button("𝕏 Adresle ara", x_search_url(address), width="stretch",
                   help="Kontrat adresi (CA) geçen en yeni gönderiler. Aynı isimli başka coinlerle karışmaz.")
    cashtag = "$" + token["symbol"].lstrip("$")  # bazı semboller zaten "$" ile başlıyor
    c2.link_button(f"𝕏 {cashtag} ara", x_search_url(cashtag), width="stretch",
                   help="Daha çok sonuç getirir; yaygın sembollerde alakasız gönderiler de çıkabilir.")
    if token["url"]:
        c3.link_button("DexScreener'da aç ↗", token["url"], width="stretch")

    if token["pair_address"]:
        with st.container(key="card-chart"):
            # DexScreener'ın gömülebilir grafiği; tarayıcı doğrudan DexScreener'dan yükler.
            st.iframe(DEXSCREENER_EMBED.format(pair=token["pair_address"]), height=650)

    left, right = st.columns([1, 1.25], gap="medium")
    with left:
        score_card(conn, address, bool(vetoes))
        if not checks:
            ui.list_card("Risk kontrolleri", [], "Henüz risk kontrolü yapılmadı. Bir sonraki risk turunda kontrol edilecek "
                                                  "(sadece hacmi en yüksek tokenlar).")
        else:
            if vetoes:
                st.error("Bu token ciddi risk taşıdığı için elendi: skor hesaplanmaz, cüzdan akışı izlenmez.")
            ui.checks_card("Risk kontrolleri", checks, risk.LEVEL_ICONS,
                           f"Son kontrol: {local_time(checks[0]['updated_at'])} ({ago(checks[0]['updated_at'])})")
    with right, st.container(key="card-wallets"):
        st.markdown("#### Cüzdan akışı")
        wallet_section(conn, token, whale_min)


def score_card(conn, address: str, vetoed: bool) -> None:
    cfg = load_config_or_none() or config.defaults()
    s = scoring.load(conn, address)
    if s is None:
        text = "Elendiği için skor hesaplanmaz." if vetoed else "Skor bir sonraki risk/akış turunda hesaplanacak."
        ui.list_card("Skor", [], text)
        return
    threshold = cfg["min_score_to_alert"]
    kind = "up" if s.score >= threshold else "muted-chip"
    bars = "".join(
        f'<div style="margin-top:12px"><div class="mr-kpi-label"><span>{ui.esc(label)}</span>'
        f'<span>{points:g} / {weight}</span></div>'
        f'<div style="height:6px; background:{ui.BORDER}; border-radius:6px; margin-top:6px">'
        f'<div style="height:6px; width:{100 * points / weight if weight else 0:.0f}%; background:{ui.LIME}; '
        f'border-radius:6px; box-shadow: 0 0 8px {ui.LIME}"></div></div></div>'
        for label, points, weight in [
            ("Whale net akışı", s.flow_points, cfg["score_weights.whale_net_flow"]),
            ("Alıcı çeşitliliği", s.buyers_points, cfg["score_weights.buyer_diversity"]),
            ("Likidite / MC", s.liquidity_points, cfg["score_weights.liquidity_to_mc"]),
        ]
    )
    penalty = (f'<div class="mr-kpi-sub" style="margin-top:12px">Risk cezası: '
               f'<span class="mr-neg">−{s.penalty:g}</span> ({len(s.warn_titles)} uyarı)</div>') if s.penalty else ""
    st.html(
        f'<div class="mr-card"><div class="mr-kpi-label"><span>Skor</span>'
        f'{ui.chip("uyarı eşiğinde" if s.score >= threshold else f"eşik {threshold}", kind)}</div>'
        f'<div class="mr-kpi-value" style="font-size:2.4rem">{s.score}<span class="mr-dim" style="font-size:1rem"> / 100</span></div>'
        f'{bars}{penalty}</div>'
    )
    st.write("")


def wallet_section(conn, token, whale_min: int) -> None:
    address = token["address"]
    if reason := flows.unsupported_reason(token):
        st.info(f"Cüzdan akışı yok: {reason}.")
        return
    state = conn.execute("SELECT updated_at FROM flow_state WHERE token = ?", (address,)).fetchone()
    if state is None:
        st.info("Cüzdan akışı henüz okunmadı. Tarama servisi bir sonraki akış turunda okuyacak "
                "(yalnızca hacmi en yüksek tokenlar izlenir; Ayarlar → 'İzlenecek en fazla token').")
        return
    st.caption(f"Sadece {ui.usd(whale_min)} ve üstü işlemler · son güncelleme {ago(state['updated_at'])}")
    wallets = flows.wallet_table(conn, address, whale_min)
    if not wallets:
        st.info(f"Bu tokenda {ui.usd(whale_min)} ve üstü alım/satım bulunamadı. "
                "Eşik Ayarlar → 'Whale eşiği' ile değiştirilebilir.".replace("$", "\\$"))
        return
    money = st.column_config.NumberColumn(format="dollar")
    st.dataframe(
        [
            {
                "Cüzdan": short_wallet(w["wallet"]),
                "Net ($)": w["net_usd"],
                "Alım ($)": w["buy_usd"],
                "Satım ($)": w["sell_usd"],
                "Alım/Satım": f"{w['buys']} / {w['sells']}",
                "İlk alım": local_time(w["first_buy"], "%d.%m %H:%M"),
                "Kalan token": w["remaining"],
                "Solscan": f"https://solscan.io/account/{w['wallet']}",
            }
            for w in wallets
        ],
        hide_index=True, width="stretch",
        column_config={
            "Alım ($)": money, "Satım ($)": money, "Net ($)": money,
            "Kalan token": st.column_config.NumberColumn(format="compact"),
            "Solscan": st.column_config.LinkColumn(display_text="aç"),
        },
    )
    st.caption("Kalan token, cüzdanın son işleminden sonra sorgulanır.")


# --- Uyarılar ---

def telegram_to_text(message: str) -> str:
    """Telegram HTML mesajını düz metne çevirir (önizleme için)."""
    return html.unescape(re.sub(r"<[^>]+>", "", message))


def page_alerts() -> None:
    cfg = load_config_or_none() or config.defaults()
    conn = db.connect()
    rows = conn.execute(
        "SELECT a.*, t.symbol, t.name, t.url FROM alerts a LEFT JOIN tokens t ON t.address = a.token "
        "ORDER BY a.sent_at DESC LIMIT 200"
    ).fetchall()
    conn.close()

    ui.header("Uyarılar", f"Skor {cfg['min_score_to_alert']} ve üstü tokenlar Telegram'a gönderilir · "
                          f"aynı token için {cfg['alert_cooldown_hours']} saat bekleme")
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    last24 = [r for r in rows if r["sent_at"] >= day_ago]
    ui.kpi_grid([
        {"label": "Uyarı (24 saat)", "value": str(len(last24)), "sub": f"Toplam {len(rows)} kayıt"},
        {"label": "Ortalama skor (24 saat)",
         "value": f"{sum(r['score'] for r in last24) / len(last24):.0f}" if last24 else "—"},
        {"label": "Gönderim", "value": "Deneme modu" if cfg["dry_run"] else "Telegram",
         "chip": ui.chip("🧪 gönderilmiyor", "warn") if cfg["dry_run"] else ui.chip("📨 açık", "up"),
         "sub": "Ayarlar → Deneme modu"},
    ])

    if not rows:
        ui.list_card("Uyarı geçmişi", [], "Henüz uyarı yok. Skoru eşiğin üstüne çıkan ilk token burada görünecek.")
        return

    with st.container(key="card-alerts"):
        st.markdown("#### Uyarı geçmişi")
        st.caption("Mesajın tamamını görmek için bir satır seçin.")
        table = [
            {
                "Zaman": local_time(r["sent_at"], "%d.%m %H:%M"),
                "Sembol": r["symbol"] or r["token"][:8],
                "İsim": r["name"] or "",
                "Skor": r["score"],
                "Gönderim": "🧪 deneme" if r["dry_run"] else "📨 Telegram",
                "Link": r["url"],
                "𝕏": x_search_url(r["token"]),
            }
            for r in rows
        ]
        event = st.dataframe(
            table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            column_config={
                "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                "Link": st.column_config.LinkColumn(display_text="DexScreener"),
                "𝕏": st.column_config.LinkColumn(display_text="ara"),
            },
        )
        if event.selection.rows:
            r = rows[event.selection.rows[0]]
            st.code(telegram_to_text(r["message"]) + "\n\nYatırım tavsiyesi değildir.", language=None, wrap_lines=True)


# --- Ayarlar ---

def setting_input(s: config.Setting, value):
    if s.type is bool:
        return st.toggle(s.label, value=value, help=s.help, key=s.key)
    return st.number_input(
        s.label, value=value, help=s.help, key=s.key, step=1,
        min_value=int(s.min) if s.min is not None else None,
        max_value=int(s.max) if s.max is not None else None,
    )


def page_settings() -> None:
    ui.header("Ayarlar", "Değişiklikler tarama servisinin bir sonraki turunda uygulanır")
    cfg = load_config_or_none()
    if cfg is None:
        st.stop()

    active = [s for s in config.SETTINGS if s.stage <= CURRENT_STAGE]
    later = [s for s in config.SETTINGS if s.stage > CURRENT_STAGE]
    groups: dict[str, list[config.Setting]] = {}
    for s in active:
        groups.setdefault(s.group, []).append(s)

    with st.form("settings", border=False):
        new_values = dict(cfg)
        cols = st.columns(2, gap="medium")
        for i, (group, items) in enumerate(groups.items()):
            with cols[i % 2].container(key=f"card-settings-{i}"):
                st.markdown(f"#### {group}")
                for s in items:
                    new_values[s.key] = setting_input(s, cfg[s.key])
        saved = st.form_submit_button("Kaydet", type="primary")

    if saved:
        try:
            config.save(new_values)
            st.success("Kaydedildi. Tarama servisi yeni ayarları bir sonraki taramada kullanacak.")
        except config.ConfigError as e:
            st.error(str(e))

    c1, c2 = st.columns(2, gap="medium")
    with c1.container(key="card-telegram"):
        st.markdown("#### Telegram testi")
        st.caption("Bot token ve chat ID'yi aşağıdaki 'Bağlantı anahtarları' bölümünden girin.")
        if st.button("📨 Test mesajı gönder"):
            try:
                ok = notify.send("👋 <b>Merhaba!</b> Bu, panelden gönderilen bir test mesajı.", cfg)
            except notify.TelegramNotConfigured as e:
                st.error(str(e))
            else:
                if not ok:
                    st.error("Gönderilemedi. Ayrıntı için terminale bakın.")
                elif cfg["dry_run"]:
                    st.info("Deneme modu açık: mesaj gönderilmedi, sadece terminale yazıldı.")
                else:
                    st.success("Gönderildi. Telegram'ı kontrol edin.")
    if later:
        with c2.container(key="card-later"):
            st.markdown("#### Sonraki aşamalarda")
            st.caption("Bu ayarlar ilgili aşama tamamlanınca düzenlenebilir hale gelecek.")
            for s in later:
                st.markdown(f"- **{s.label}** (Aşama {s.stage}): `{cfg[s.key]}`")

    keys_section()


KEY_STATUS = {
    "kasa": ("✅", "Kayıtlı (şifreli kasada)"),
    "dosya": ("⚠️", ".env dosyasında düz metin — kasaya taşıyın"),
    None: ("❌", "Girilmemiş"),
}


def keys_section() -> None:
    """Gizli anahtarların panelden girilmesi. Değerler asla gösterilmez."""
    with st.container(key="card-keys"):
        st.markdown("#### Bağlantı anahtarları")
        vault = "Mac Anahtar Zinciri" if sys.platform == "darwin" else "Windows Kimlik Bilgisi Yöneticisi" \
            if sys.platform == "win32" else "işletim sistemi kasası"
        st.caption(f"Anahtarlar {vault}'nde şifreli saklanır; hiçbir proje dosyasında durmaz ve panelde gösterilmez. "
                   "Kaydetmeden önce çalıştıkları denenir.")
        if not keys.vault_available():
            st.warning("Bu bilgisayarda şifreli kasa bulunamadı. Anahtarlar .env dosyasından okunmaya devam eder.")
            return

        in_file = [name for name in keys.NAMES if keys.source(name) == "dosya"]
        if in_file:
            st.warning("Bazı anahtarlar hâlâ .env dosyasında düz metin olarak duruyor.")
            if st.button("🔐 .env'deki anahtarları kasaya taşı", type="primary"):
                moved = keys.move_file_keys_to_vault()
                st.success(f"{len(moved)} anahtar kasaya taşındı ve .env dosyasından silindi.")
                st.rerun()

        for name, label, help_text in keys.KEYS:
            icon, status_text = KEY_STATUS[keys.source(name)]
            st.markdown(f"**{label}** · {icon} {status_text}")
            with st.form(f"form-{name}", clear_on_submit=True, border=False):
                c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
                value = c1.text_input(label, type="password", placeholder="Yeni değer yapıştırın",
                                      help=help_text, label_visibility="collapsed")
                submitted = c2.form_submit_button("Kaydet", width="stretch")
            if submitted:
                save_key(name, value)
            if name == "TELEGRAM_CHAT_ID" and keys.get("TELEGRAM_BOT_TOKEN"):
                chat_id_finder()
            if keys.source(name) == "kasa":
                if st.button(f"Sil", key=f"del-{name}", type="tertiary", help=f"{label} kasadan silinir"):
                    keys.remove(name)
                    st.rerun()
            st.write("")


def save_key(name: str, value: str) -> None:
    value = value.strip()
    if not value:
        st.error("Boş değer kaydedilmedi.")
        return
    try:
        if name == "TELEGRAM_BOT_TOKEN":
            bot = notify.check_bot_token(value)
            note = f"@{bot} doğrulandı."
        elif name == "HELIUS_API_KEY":
            helius.check_key(value)
            note = "Helius anahtarı doğrulandı."
        else:
            if not re.fullmatch(r"-?\d+", value):
                st.error("Chat ID sadece rakamlardan oluşur (grup ise başında '-' olabilir).")
                return
            note = "Chat ID kaydedildi."
    except (notify.TelegramNotConfigured, helius.HeliusError) as e:
        st.error(f"Kaydedilmedi: {e}")
        return
    keys.save(name, value)
    st.success(note + " Tarama servisi bir sonraki turda yeni anahtarı kullanır.")


def chat_id_finder() -> None:
    with st.expander("Chat ID'mi bilmiyorum"):
        st.caption("Telegram'da bot'unuza herhangi bir mesaj yazın (ör. 'merhaba'), sonra aşağıdaki düğmeye basın.")
        if st.button("Bot'a yazanları bul", key="find-chat"):
            try:
                st.session_state["chats"] = notify.find_chat_ids()
            except notify.TelegramNotConfigured as e:
                st.error(str(e))
        chats = st.session_state.get("chats")
        if chats == []:
            st.info("Kimse bulunamadı. Bot'a bir mesaj yazıp tekrar deneyin.")
        for chat_id, chat_name in chats or []:
            if st.button(f"Bunu kullan: {chat_name or 'isimsiz'} ({chat_id})", key=f"use-{chat_id}"):
                keys.save("TELEGRAM_CHAT_ID", chat_id)
                st.session_state.pop("chats", None)
                st.rerun()


# --- Sistem ---

def page_system() -> None:
    conn = db.connect()
    status = db.get_status(conn)
    credits_today = db.usage_today(conn, helius.SERVICE)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    credits_month = conn.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM api_usage WHERE service = ? AND day LIKE ?", (helius.SERVICE, f"{month}%")
    ).fetchone()[0]
    conn.close()
    cfg = load_config_or_none() or config.defaults()

    ui.header("Sistem", "Tarama servisi, API kullanımı ve kayıtlar", service_pill(status))
    ui.kpi_grid([
        {"label": "Son tarama", "value": local_time(status.get("last_scan_at"), "%H:%M"), "sub": ago(status.get("last_scan_at"))},
        {"label": "Son risk turu", "value": local_time(status.get("last_risk_at"), "%H:%M"), "sub": ago(status.get("last_risk_at"))},
        {"label": "Son akış turu", "value": local_time(status.get("last_flow_at"), "%H:%M"), "sub": ago(status.get("last_flow_at"))},
        {"label": "Başlama", "value": local_time(status.get("started_at"), "%H:%M"), "sub": local_time(status.get("started_at"), "%d.%m.%Y")},
    ])

    budget = cfg["helius_daily_credit_budget"]
    c1, c2 = st.columns(2, gap="medium")
    with c1.container(key="card-helius"):
        st.markdown("#### Helius kredisi (tahmini)")
        st.progress(min(credits_today / budget, 1.0),
                    text=f"Bugün {credits_today:,} / {budget:,} (%{100 * credits_today / budget:.0f})")
        st.progress(min(credits_month / 1_000_000, 1.0), text=f"Bu ay {credits_month:,} / 1.000.000 (ücretsiz plan)")
    with c2.container(key="card-config"):
        st.markdown("#### Bağlantılar")
        st.markdown(("✅" if notify.is_configured() else "❌") + " Telegram")
        st.markdown(("✅" if helius.is_configured() else "❌") + " Helius (cüzdan akışı ve dev satışı)")
        st.markdown(("🧪 Deneme modu açık: Telegram'a mesaj gönderilmiyor" if cfg["dry_run"]
                     else "📨 Telegram mesajları gönderiliyor"))
        if status.get("last_error"):
            st.warning(f"Son hata: {status['last_error']}")

    with st.container(key="card-logs"):
        st.markdown("#### Son kayıtlar")
        lines = logs.tail(100)
        st.code("\n".join(lines) if lines else "Henüz log yok.", language=None, height=380, wrap_lines=True)
        if st.button("🔄 Yenile"):
            st.rerun()


# --- Uygulama ---

ui.inject_css()
st.logo(str(LOGO), size="large")
nav = st.navigation([
    st.Page(page_overview, title="Genel Bakış", icon=":material/space_dashboard:", default=True),
    st.Page(page_tokens, title="Tokenlar", icon=":material/toll:", url_path="tokenlar"),
    st.Page(page_alerts, title="Uyarılar", icon=":material/notifications:", url_path="uyarilar"),
    st.Page(page_settings, title="Ayarlar", icon=":material/tune:", url_path="ayarlar"),
    st.Page(page_system, title="Sistem", icon=":material/monitor_heart:", url_path="sistem"),
])
st.sidebar.caption(f"Sürüm {VERSION} · Aşama {CURRENT_STAGE}")
st.sidebar.caption("Sadece izleme yapar. Yatırım tavsiyesi değildir.")
nav.run()
