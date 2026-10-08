#!/bin/bash
# Memecoin Radar — 7/24 çalışma için Mac servis kurulumu. Finder'da çift tıklayın.
#
# Üç arka plan servisi (launchd "LaunchAgent") kurar:
#   com.memecoinradar.scanner  tarama servisi (main.py)
#   com.memecoinradar.panel    panel (http://127.0.0.1:8501)
#   com.memecoinradar.awake    Mac'in boşta uykuya geçmesini engeller
# Servisler kullanıcı oturumu açılınca kendiliğinden başlar; çökerse macOS yeniden başlatır.
# Panel güncelleme sonrası kapanınca da macOS onu yeniden açar.
# Geri almak için: servis_kaldir.command

cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

if [ ! -x ".venv/bin/python" ]; then
    echo "Sanal ortam bulunamadı, kuruluyor (ilk seferde birkaç dakika sürebilir)..."
    python3 -m venv .venv || { echo "Python bulunamadı. python.org'dan Python kurun."; read -r; exit 1; }
    .venv/bin/pip install -r requirements.txt || { echo "Paketler kurulamadı."; read -r; exit 1; }
fi

# Elle açılmış bir kopya çalışıyorsa çakışmasın.
if lsof -nP -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl print "gui/$UID_NUM/com.memecoinradar.panel" >/dev/null 2>&1; then
    echo "Panel şu an start.command ile açık görünüyor. Önce o pencereyi kapatın (Ctrl+C), sonra bunu tekrar çalıştırın."
    read -r; exit 1
fi

mkdir -p "$AGENTS" logs

# $1: etiket, $2: program ve argümanlar (XML dizisi), $3: hata log dosyası adı
# Normal kayıtlar logs/radar.log'a (boyutu sınırlı) yazılır; servis loguna sadece hatalar gider.
write_agent() {
    cat > "$AGENTS/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$1</string>
    <key>ProgramArguments</key>
    <array>$2</array>
    <key>WorkingDirectory</key><string>$DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>15</integer>
    <key>StandardOutPath</key><string>/dev/null</string>
    <key>StandardErrorPath</key><string>$DIR/logs/$3</string>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
</dict>
</plist>
PLIST
    plutil -lint "$AGENTS/$1.plist" >/dev/null || { echo "Servis dosyası hatalı: $1"; read -r; exit 1; }
}

write_agent com.memecoinradar.scanner \
    "<string>$DIR/.venv/bin/python</string><string>$DIR/main.py</string>" service-scanner.log
write_agent com.memecoinradar.panel \
    "<string>$DIR/.venv/bin/python</string><string>-m</string><string>streamlit</string><string>run</string><string>$DIR/panel.py</string><string>--server.headless</string><string>true</string>" \
    service-panel.log
write_agent com.memecoinradar.awake \
    "<string>/usr/bin/caffeinate</string><string>-i</string><string>-s</string>" service-awake.log

for label in com.memecoinradar.awake com.memecoinradar.scanner com.memecoinradar.panel; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null
    launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$label.plist" || { echo "Servis başlatılamadı: $label"; read -r; exit 1; }
done

echo "Servisler kuruldu ve başlatıldı. Panel birkaç saniye içinde açılıyor..."
sleep 6
open "http://127.0.0.1:8501"
echo
echo "Bu pencereyi kapatabilirsiniz; program arka planda çalışmaya devam eder."
echo "Durdurmak/kaldırmak için: servis_kaldir.command"
read -r -p "Kapatmak için Enter'a basın..."
