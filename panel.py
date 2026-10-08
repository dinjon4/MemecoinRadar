"""Memecoin Radar yerel paneli. Sadece bu bilgisayardan açılır (127.0.0.1).

Çalıştırma:  streamlit run panel.py
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from radar import CURRENT_STAGE, VERSION, config, db, flows, logs, notify
from radar.sources import helius

TZ = ZoneInfo("Europe/Istanbul")
# Tarama servisi bekleme sırasında 30 sn'de bir sinyal yazar; bundan uzun sessizlik = durmuş.
ALIVE_SECONDS = 90

logs.setup(to_file=False)
st.set_page_config(page_title="Memecoin Radar", page_icon="📡", layout="wide")


def local_time(iso: str | None) -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S")


def ago(iso: str | None) -> str:
    if not iso:
        return ""
    seconds = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())
    if seconds < 60:
        return f"{seconds} sn önce"
    if seconds < 3600:
        return f"{seconds // 60} dk önce"
    return f"{seconds // 3600} sa {seconds % 3600 // 60} dk önce"


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


def page_status() -> None:
    st.title("📡 Durum")
    conn = db.connect()
    status = db.get_status(conn)
    helius_today = db.usage_today(conn, helius.SERVICE)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    helius_month = conn.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM api_usage WHERE service = ? AND day LIKE ?", (helius.SERVICE, f"{month}%")
    ).fetchone()[0]
    conn.close()
    cfg = load_config_or_none()

    if is_alive(status):
        st.success("Tarama servisi **çalışıyor**")
    else:
        st.error("Tarama servisi **çalışmıyor**. Başlatmak için start.command (Mac) veya start.bat (Windows).")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.caption("Son tarama")
        st.markdown(f"**{local_time(status.get('last_scan_at'))}**  \n{ago(status.get('last_scan_at'))}")
    with c2.container(border=True):
        st.caption("Başlama zamanı")
        st.markdown(f"**{local_time(status.get('started_at'))}**  \n{ago(status.get('started_at'))}")

    st.subheader("Helius kredi kullanımı (tahmini)")
    budget = cfg["helius_daily_credit_budget"] if cfg else 30000
    c1, c2, c3 = st.columns(3)
    c1.metric("Bugün", f"{helius_today:,}", help=f"Günlük bütçe: {budget:,}")
    c2.metric("Bu ay", f"{helius_month:,}", help="Ücretsiz plan: ayda 1.000.000")
    c3.metric("Son akış turu", local_time(status.get("last_flow_at"))[11:16] or "—",
              help=ago(status.get("last_flow_at")) or None)
    st.progress(min(helius_today / budget, 1.0), text=f"Günlük bütçenin %{100 * helius_today / budget:.0f}'i kullanıldı")
    if not helius.is_configured():
        st.warning("Helius ayarlanmamış: .env dosyasında HELIUS_API_KEY olmalı. Cüzdan akışı çalışmaz.")

    if status.get("last_error"):
        st.warning(f"Son hata: {status['last_error']}")
    if cfg and cfg["dry_run"]:
        st.info("Deneme modu açık: Telegram'a mesaj gönderilmiyor.")
    if not notify.is_configured():
        st.warning("Telegram ayarlanmamış: .env dosyasında TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID olmalı.")

    st.subheader("Son log kayıtları")
    st.caption("En yeni kayıt en altta.")
    lines = logs.tail(100)
    st.code("\n".join(lines) if lines else "Henüz log yok.", language=None, height=400, wrap_lines=True)
    if st.button("🔄 Yenile"):
        st.rerun()


def page_tokens() -> None:
    st.title("🪙 Tokenlar")
    cfg = load_config_or_none()
    max_age = cfg["token_max_age_hours"] if cfg else 24

    c1, c2 = st.columns([1, 2])
    show_filtered = c1.toggle("Elenenleri de göster", value=False)
    query = c2.text_input("Ara (sembol, isim veya adres)", placeholder="ör. BONK").strip().lower()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age)).isoformat(timespec="seconds")
    whale_min = cfg["whale_min_usd"] if cfg else 5000
    conn = db.connect()
    rows = conn.execute(
        "SELECT * FROM tokens WHERE created_at >= ? ORDER BY created_at DESC", (cutoff,)
    ).fetchall()
    whale_net = {
        r["token"]: (r["net"], r["n"])
        for r in conn.execute(
            "SELECT token, SUM(CASE WHEN side = 'buy' THEN usd ELSE -usd END) AS net, COUNT(*) AS n "
            "FROM trades WHERE usd >= ? GROUP BY token", (whale_min,)
        )
    }

    passed_count = sum(r["passed"] for r in rows)
    st.caption(f"Son {max_age} saatte açılmış {len(rows)} token görüldü; {passed_count} tanesi filtreleri geçti.")

    now = datetime.now(timezone.utc)
    table = []
    for r in rows:
        if not show_filtered and not r["passed"]:
            continue
        if query and query not in f"{r['symbol']} {r['name']} {r['address']}".lower():
            continue
        table.append({
            "Durum": "✅" if r["passed"] else "⛔",
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
            "Adres": r["address"],
        })

    if not table:
        st.info("Gösterilecek token yok. Tarama servisi çalışıyor mu? (Durum sayfası)")
        conn.close()
        return

    money = st.column_config.NumberColumn(format="compact")
    st.caption("Ayrıntı için bir satırın solundaki kutuyu seçin.")
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_order=[c for c in table[0] if show_filtered or c != "Eleme sebebi"],
        column_config={
            "MC ($)": money,
            "Likidite ($)": money,
            "Hacim 24s ($)": money,
            "Whale net ($)": money,
            "Link": st.column_config.LinkColumn(display_text="DexScreener"),
        },
    )
    if event.selection.rows:
        token_detail(conn, table[event.selection.rows[0]]["Adres"], whale_min)
    conn.close()


def short_wallet(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}"


def token_detail(conn, address: str, whale_min: int) -> None:
    token = conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()
    st.divider()
    st.subheader(f"{token['symbol']} — {token['name']}")
    st.caption(f"Adres: `{address}`")

    if reason := flows.unsupported_reason(token):
        st.info(f"Cüzdan akışı yok: {reason}.")
        return
    state = conn.execute("SELECT updated_at FROM flow_state WHERE token = ?", (address,)).fetchone()
    if state is None:
        st.info("Cüzdan akışı henüz okunmadı. Tarama servisi bir sonraki akış turunda okuyacak "
                "(yalnızca hacmi en yüksek tokenlar izlenir; Ayarlar → 'Akışı izlenecek en fazla token').")
        return

    s = flows.token_summary(conn, address, whale_min)
    c1, c2, c3 = st.columns(3)
    c1.metric("Whale net akış", f"{'+' if s['net_usd'] >= 0 else '-'}${abs(s['net_usd']):,.0f}",
              help="Whale büyüklüğündeki alımlar eksi satımlar. Artı = para giriyor.")
    c2.metric("Alıcı / satıcı cüzdan", f"{s['buyers']} / {s['sellers']}")
    c3.metric("Whale işlem", s["trades"], help=f"${whale_min:,} ve üstü alım/satımlar")
    st.caption(f"Akış son güncelleme: {local_time(state['updated_at'])} ({ago(state['updated_at'])})")

    wallets = flows.wallet_table(conn, address, whale_min)
    if not wallets:
        st.info(f"Bu tokenda ${whale_min:,} ve üstü alım/satım bulunamadı. "
                "Eşik Ayarlar → 'Whale eşiği' ile değiştirilebilir.")
        return
    money = st.column_config.NumberColumn(format="dollar")
    st.dataframe(
        [
            {
                "Cüzdan": short_wallet(w["wallet"]),
                "Alım ($)": w["buy_usd"],
                "Satım ($)": w["sell_usd"],
                "Net ($)": w["net_usd"],
                "Alım/Satım": f"{w['buys']} / {w['sells']}",
                "İlk alım": local_time(w["first_buy"]),
                "Kalan token": w["remaining"],
                "Solscan": f"https://solscan.io/account/{w['wallet']}",
            }
            for w in wallets
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Alım ($)": money, "Satım ($)": money, "Net ($)": money,
            "Kalan token": st.column_config.NumberColumn(format="compact"),
            "Solscan": st.column_config.LinkColumn(display_text="aç"),
        },
    )
    st.caption("Sadece whale büyüklüğündeki işlemler sayılır; küçük işlemler bu tabloya girmez. "
               "Kalan token, cüzdanın son işleminden sonra sorgulanır.")


def setting_input(s: config.Setting, value):
    if s.type is bool:
        return st.toggle(s.label, value=value, help=s.help, key=s.key)
    return st.number_input(
        s.label, value=value, help=s.help, key=s.key, step=1,
        min_value=int(s.min) if s.min is not None else None,
        max_value=int(s.max) if s.max is not None else None,
    )


def page_settings() -> None:
    st.title("⚙️ Ayarlar")
    cfg = load_config_or_none()
    if cfg is None:
        st.stop()

    active = [s for s in config.SETTINGS if s.stage <= CURRENT_STAGE]
    later = [s for s in config.SETTINGS if s.stage > CURRENT_STAGE]

    with st.form("settings"):
        new_values = dict(cfg)
        group = None
        for s in active:
            if s.group != group:
                group = s.group
                st.subheader(group)
            new_values[s.key] = setting_input(s, cfg[s.key])
        saved = st.form_submit_button("💾 Kaydet", type="primary")

    if saved:
        try:
            config.save(new_values)
            st.success("Kaydedildi. Tarama servisi yeni ayarları bir sonraki taramada kullanacak.")
        except config.ConfigError as e:
            st.error(str(e))

    if later:
        with st.expander("Sonraki aşamalarda kullanılacak ayarlar"):
            st.caption("Bu ayarlar ilgili aşama tamamlanınca burada düzenlenebilir hale gelecek.")
            for s in later:
                st.markdown(f"- **{s.label}** (Aşama {s.stage}): `{cfg[s.key]}`")

    st.divider()
    st.subheader("Telegram")
    st.caption("Bot token ve chat ID güvenlik için panelde gösterilmez; .env dosyasında durur.")
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


nav = st.navigation([
    st.Page(page_status, title="Durum", icon="📡", default=True),
    st.Page(page_tokens, title="Tokenlar", icon="🪙", url_path="tokenlar"),
    st.Page(page_settings, title="Ayarlar", icon="⚙️", url_path="ayarlar"),
])
st.sidebar.caption(f"Memecoin Radar {VERSION} · Aşama {CURRENT_STAGE}")
st.sidebar.caption("Sadece izleme yapar. Yatırım tavsiyesi değildir.")
nav.run()
