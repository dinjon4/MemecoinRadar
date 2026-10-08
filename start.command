#!/bin/bash
# Memecoin Radar — Mac başlatıcı. Finder'da çift tıklayın.
# Tarama servisini ve paneli başlatır, paneli tarayıcıda açar. Kapatmak için bu pencerede Ctrl+C.

cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "Sanal ortam bulunamadı, kuruluyor (ilk seferde birkaç dakika sürebilir)..."
    python3 -m venv .venv || { echo "Python bulunamadı. python.org'dan Python kurun."; read -r; exit 1; }
    .venv/bin/pip install -r requirements.txt || { echo "Paketler kurulamadı."; read -r; exit 1; }
fi

if [ ! -f ".env" ]; then
    echo "UYARI: .env dosyası yok. Telegram mesajları gönderilemez. .env.example dosyasını .env olarak kopyalayıp doldurun."
fi

.venv/bin/python main.py &
SCANNER_PID=$!
trap 'kill $SCANNER_PID 2>/dev/null; wait $SCANNER_PID 2>/dev/null' EXIT

.venv/bin/python -m streamlit run panel.py
