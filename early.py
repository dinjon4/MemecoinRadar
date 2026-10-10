"""Memecoin Radar — Erken Hacim servisi (Aşama 8). Tarama servisinden (main.py) ayrı bir süreçtir.

Ayarlarda "Erken hacim veri toplama" açıkken her dakika yeni ve hareketlenen havuzların hacim/alıcı
verisini kaydeder. Kapalıyken hiçbir istek yapmaz, sadece ayarın açılmasını bekler.
Şimdilik uyarı göndermez; toplanan veriler panelde "Erken Hacim" sayfasında görünür.

Kullanım:
    python early.py          # sürekli çalışır (Ctrl+C ile durur)
    python early.py --once   # ayar kapalı olsa da tek tur veri toplayıp çıkar
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from radar import EARLY_LOG_PATH, config, db, logs, updater
from radar.early import collect

log = logging.getLogger("radar.early")

# Panelin "çalışıyor" görmesi için bekleme sırasında bu aralıkla durum yazılır.
HEARTBEAT_SECONDS = 30
# Ayar kapalıyken bu aralıkla tekrar bakılır.
IDLE_SECONDS = 60


class RestartRequested(Exception):
    """Panel güncelleme yaptı; servis yeni kodla yeniden başlamalı."""


def load_config(last_good: dict | None) -> dict:
    """Ayarları okur. Dosya hatalıysa son geçerli ayarlarla (ilk açılışta varsayılanlarla) devam eder."""
    try:
        return config.load()
    except config.ConfigError as e:
        log.error("%s\nSon geçerli ayarlarla devam ediliyor.", e)
        return last_good or config.defaults()


def restart_requested(conn, started_at: str) -> bool:
    requested = db.get_status(conn).get("restart_requested_at")
    return bool(requested) and requested > started_at


def wait(conn, seconds: float, started_at: str) -> None:
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        time.sleep(min(HEARTBEAT_SECONDS, remaining))
        db.set_status(conn, "early_heartbeat_at", db.utc_now())
        if restart_requested(conn, started_at):
            raise RestartRequested


def run_once(conn, cfg: dict) -> collect.RoundResult:
    started = time.monotonic()
    result = collect.run_round(conn, cfg)
    log.info("Erken hacim turu: %d havuz listede (%d yeni), %d havuz ölçüldü, %d anlık görüntü (%.0f sn).",
             result.listed, result.new, result.followed, result.snapshots, time.monotonic() - started)
    return result


def _stop_on_signal(signum, frame):
    raise KeyboardInterrupt


def run_forever() -> None:
    signal.signal(signal.SIGTERM, _stop_on_signal)
    if hasattr(signal, "SIGHUP"):  # Windows'ta yok
        signal.signal(signal.SIGHUP, _stop_on_signal)
    conn = db.connect()
    started_at = db.utc_now()
    db.set_status(conn, "early_started_at", started_at)
    db.set_status(conn, "early_stopped_at", None)
    cfg = None
    restart = False
    was_enabled = None
    log.info("Erken Hacim servisi %s başladı. Durdurmak için Ctrl+C.", updater.current_version())
    try:
        while True:
            cfg = load_config(cfg)
            enabled = cfg["early_enabled"]
            if enabled != was_enabled:
                log.info("Erken hacim veri toplama %s.", "açık" if enabled else
                         "kapalı (Panel → Ayarlar → Erken Hacim'den açılabilir)")
                was_enabled = enabled
            db.set_status(conn, "early_enabled", int(enabled))
            if not enabled:
                db.set_status(conn, "early_heartbeat_at", db.utc_now())
                wait(conn, IDLE_SECONDS, started_at)
                continue
            round_started = time.monotonic()
            try:
                run_once(conn, cfg)
                db.set_status(conn, "early_last_run_at", db.utc_now())
                db.set_status(conn, "early_last_error", None)
            except Exception as e:
                # Bir turdaki hata servisi durdurmasın; sonraki turda tekrar denenir.
                log.exception("Erken hacim turunda hata")
                db.set_status(conn, "early_last_error", f"{db.utc_now()} {type(e).__name__}: {e}")
            db.set_status(conn, "early_heartbeat_at", db.utc_now())
            # Tur süresi aralıktan düşülür: tur 20 sn sürdüyse 40 sn beklenir.
            wait(conn, max(5, cfg["early_interval_seconds"] - (time.monotonic() - round_started)), started_at)
    except KeyboardInterrupt:
        log.info("Durduruldu.")
    except RestartRequested:
        restart = True
    finally:
        if not restart:
            db.set_status(conn, "early_stopped_at", db.utc_now())
        conn.close()
    if restart:
        log.info("Güncelleme sonrası yeniden başlatılıyor...")
        logging.shutdown()
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> None:
    parser = argparse.ArgumentParser(description="Memecoin Radar erken hacim servisi")
    parser.add_argument("--once", action="store_true", help="tek tur veri toplayıp çık (ayar kapalı olsa da)")
    args = parser.parse_args()
    logs.setup(path=EARLY_LOG_PATH)
    if args.once:
        conn = db.connect()
        run_once(conn, load_config(None))
        conn.close()
        return
    run_forever()


if __name__ == "__main__":
    main()
