"""Memecoin Radar tarama servisi.

Kullanım:
    python main.py                  # sürekli tarama (Ctrl+C ile durur)
    python main.py --once           # tek tarama yapıp çıkar
    python main.py --test-telegram  # Telegram'a deneme mesajı gönderir
    python main.py --find-chat-id   # Telegram chat ID'nizi bulur
    python main.py --token ADRES    # bir tokenın cüzdan akışı tablosu
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

from radar import VERSION, config, db, discovery, flows, logs, notify, risk
from radar.sources import helius

log = logging.getLogger("radar")

# Bekleme sırasında panelin "çalışıyor" görmesi için bu aralıkla durum güncellenir.
HEARTBEAT_SECONDS = 30


def run_scan(conn, cfg: dict, force_flow: bool = False) -> discovery.ScanResult:
    """Tek bir tarama turu: token tespiti, sırası geldiyse cüzdan akışı.
    Sonraki aşamalarda risk ve skor adımları buraya eklenecek."""
    result = discovery.scan(conn, cfg)

    # Risk akıştan önce: veto alan tokenların akışı izlenmez (kredi tasarrufu).
    if force_flow or is_due(conn, "last_risk_at", cfg["risk_interval_minutes"]):
        risk.run(conn, cfg)
        db.set_status(conn, "last_risk_at", db.utc_now())
    if force_flow or is_due(conn, "last_flow_at", cfg["flow_interval_minutes"]):
        flows.run(conn, cfg)
        db.set_status(conn, "last_flow_at", db.utc_now())
    return result


def is_due(conn, status_key: str, interval_minutes: int) -> bool:
    last = db.get_status(conn).get(status_key)
    return not last or datetime.now(timezone.utc) - datetime.fromisoformat(last) >= timedelta(minutes=interval_minutes)


def show_token(conn, cfg: dict, address: str) -> None:
    """Tek bir tokenın cüzdan akışını şimdi günceller ve terminale yazar."""
    token = conn.execute("SELECT * FROM tokens WHERE address = ?", (address,)).fetchone()
    if token is None:
        log.error("Bu token veritabanında yok. Önce tarama servisinin onu bulmuş olması gerekir.")
        sys.exit(1)
    print(f"\n{token['symbol']} ({token['name']}) — risk kontrolleri")
    risk.check_token(conn, cfg, token)
    print(risk.format_checks(risk.checks_for(conn, address)))

    if reason := flows.unsupported_reason(token):
        print(f"\nCüzdan akışı yok: {reason}.")
        return
    try:
        flows.update_token(conn, cfg, token)
    except helius.HeliusError as e:
        log.error("%s", e)
        sys.exit(1)
    whale = cfg["whale_min_usd"]
    s = flows.token_summary(conn, address, whale)
    print(f"\n{token['symbol']} ({token['name']}) — whale eşiği ${whale:,}")
    print(f"Whale net akış: {'+' if s['net_usd'] >= 0 else '-'}${abs(s['net_usd']):,.0f} "
          f"(alım ${s['buy_usd']:,.0f} / satım ${s['sell_usd']:,.0f}; "
          f"{s['buyers']} alıcı, {s['sellers']} satıcı cüzdan, {s['trades']} işlem)\n")
    print(flows.format_wallet_table(flows.wallet_table(conn, address, whale)))
    print(f"\nBugünkü Helius kullanımı: ~{db.usage_today(conn, helius.SERVICE)} kredi")


def load_config(last_good: dict | None) -> dict:
    """Ayarları okur. Dosya hatalıysa son geçerli ayarlarla devam eder; ilk açılışta hatalıysa çıkar."""
    try:
        return config.load()
    except config.ConfigError as e:
        if last_good is None:
            log.error("%s", e)
            sys.exit(1)
        log.error("%s\nSon geçerli ayarlarla devam ediliyor.", e)
        return last_good


def wait(conn, minutes: int) -> None:
    deadline = time.monotonic() + minutes * 60
    while (remaining := deadline - time.monotonic()) > 0:
        time.sleep(min(HEARTBEAT_SECONDS, remaining))
        db.set_status(conn, "heartbeat_at", db.utc_now())


def _stop_on_signal(signum, frame):
    raise KeyboardInterrupt


def run_forever() -> None:
    # Başlatıcı kapatırken gönderdiği sinyaller de Ctrl+C gibi temiz kapanışa gitsin.
    signal.signal(signal.SIGTERM, _stop_on_signal)
    if hasattr(signal, "SIGHUP"):  # Windows'ta yok
        signal.signal(signal.SIGHUP, _stop_on_signal)
    conn = db.connect()
    db.set_status(conn, "started_at", db.utc_now())
    db.set_status(conn, "pid", os.getpid())
    db.set_status(conn, "stopped_at", None)
    cfg = None
    log.info("Memecoin Radar %s başladı. Durdurmak için Ctrl+C.", VERSION)
    try:
        while True:
            cfg = load_config(cfg)
            if cfg["dry_run"]:
                log.info("Deneme modu açık: Telegram'a mesaj gönderilmeyecek.")
            try:
                run_scan(conn, cfg)
                db.set_status(conn, "last_scan_at", db.utc_now())
                db.set_status(conn, "last_error", None)
            except Exception as e:
                # Bir turdaki hata servisi durdurmasın; bir sonraki turda tekrar denenir.
                log.exception("Tarama sırasında hata")
                db.set_status(conn, "last_error", f"{db.utc_now()} {type(e).__name__}: {e}")
            db.set_status(conn, "heartbeat_at", db.utc_now())
            wait(conn, cfg["scan_interval_minutes"])
    except KeyboardInterrupt:
        log.info("Durduruldu.")
    finally:
        db.set_status(conn, "stopped_at", db.utc_now())
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Memecoin Radar tarama servisi")
    parser.add_argument("--once", action="store_true", help="tek tarama yapıp çık")
    parser.add_argument("--test-telegram", action="store_true", help="Telegram'a deneme mesajı gönder")
    parser.add_argument("--find-chat-id", action="store_true", help="bot'a mesaj atan sohbetlerin chat ID'sini göster")
    parser.add_argument("--token", metavar="ADRES", help="bir tokenın cüzdan akışını güncelle ve göster")
    args = parser.parse_args()

    logs.setup()

    if args.token:
        cfg = load_config(None)
        conn = db.connect()
        show_token(conn, cfg, args.token.strip())
        conn.close()
        return

    if args.find_chat_id:
        try:
            chats = notify.find_chat_ids()
        except notify.TelegramNotConfigured as e:
            log.error("%s", e)
            sys.exit(1)
        if not chats:
            print("Sohbet bulunamadı. Telegram'da bot'unuza bir mesaj (ör. 'merhaba') yazıp tekrar deneyin.")
        for chat_id, name in chats:
            print(f"Chat ID: {chat_id}   ({name})")
        return

    if args.test_telegram:
        cfg = load_config(None)
        try:
            ok = notify.send("👋 <b>Merhaba!</b> Memecoin Radar Telegram bağlantısı çalışıyor.", cfg)
        except notify.TelegramNotConfigured as e:
            log.error("%s. .env.example dosyasını .env olarak kopyalayıp doldurun.", e)
            ok = False
        sys.exit(0 if ok else 1)

    if args.once:
        cfg = load_config(None)
        conn = db.connect()
        result = run_scan(conn, cfg, force_flow=True)
        db.set_status(conn, "last_scan_at", db.utc_now())
        conn.close()
        print()
        print(discovery.format_table(result.passed))
        return

    run_forever()


if __name__ == "__main__":
    main()
