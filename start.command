#!/bin/bash
# Memecoin Radar — Mac başlatıcı. Finder'da çift tıklayın.
# Tarama servisini ve paneli başlatır, paneli tarayıcıda açar.
# Bu pencere açık kaldığı sürece Mac kendiliğinden uykuya geçmez (kapak kapanınca yine uyur).
# Durdurmak için: bu pencerede Ctrl+C veya pencereyi kapatın. Her şey kapanır, Mac normal uyku ayarına döner.

cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "Sanal ortam bulunamadı, kuruluyor (ilk seferde birkaç dakika sürebilir)..."
    python3 -m venv .venv || { echo "Python bulunamadı. python.org'dan Python kurun."; read -r; exit 1; }
    .venv/bin/pip install -r requirements.txt || { echo "Paketler kurulamadı."; read -r; exit 1; }
fi

.venv/bin/python main.py &
SCANNER_PID=$!

# Uyku engeli: -i = boşta kalınca uyuma (ekran yine kararabilir).
# -w: bu betik herhangi bir şekilde biterse caffeinate de kendiliğinden biter.
caffeinate -i -w $$ &
CAFFEINATE_PID=$!

cleanup() {
    trap - EXIT
    echo "Kapatılıyor..."
    kill $SCANNER_PID $CAFFEINATE_PID 2>/dev/null
    wait $SCANNER_PID 2>/dev/null
}
trap cleanup EXIT
# Ctrl+C (INT), pencere kapatma (HUP) ve sonlandırma (TERM) hepsi temiz kapanışa gider.
trap 'exit 0' INT HUP TERM

echo "Çalışıyor. Mac bu pencere açıkken uykuya geçmeyecek. Durdurmak için Ctrl+C."
# Panel güncelleme yaptıktan sonra 75 koduyla kapanır; o zaman yeniden açılır
# (tarayıcıda yeni sekme açmadan; açık sayfa kendiliğinden yeniden bağlanır).
HEADLESS=false
while true; do
    .venv/bin/python -m streamlit run panel.py --server.headless $HEADLESS
    [ $? -eq 75 ] || break
    echo "Güncelleme yapıldı, panel yeniden başlatılıyor..."
    HEADLESS=true
done
