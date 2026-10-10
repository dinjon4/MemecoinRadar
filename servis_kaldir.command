#!/bin/bash
# Memecoin Radar — 7/24 servislerini durdurur ve kaldırır. Finder'da çift tıklayın.
# Verileriniz, ayarlarınız ve anahtarlarınız silinmez; sadece arka plan servisleri kaldırılır.

UID_NUM="$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"

for label in com.memecoinradar.panel com.memecoinradar.scanner com.memecoinradar.early com.memecoinradar.awake; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null && echo "Durduruldu: $label"
    rm -f "$AGENTS/$label.plist"
done

echo
echo "Servisler kaldırıldı. Programı tekrar elle açmak için start.command, 7/24 için servis_kur.command."
read -r -p "Kapatmak için Enter'a basın..."
