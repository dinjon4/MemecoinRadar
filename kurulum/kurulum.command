#!/bin/bash
# Memecoin Radar — Mac için tek adımda kurulum.
#
# Kullanım (ikisinden biri):
#   1) Bu dosyaya çift tıklayın (Mac uyarı verirse: sağ tık → Aç).
#   2) Terminal'e tek satır:  curl -fsSL <bu dosyanın herkese açık adresi> | bash
#
# Yaptıkları: eksikse Python, git (Xcode araçları) ve GitHub aracını (gh) kurar; GitHub'a giriş ister (bir kez,
# tarayıcıda); programı ~/MemecoinRadar klasörüne indirir; paketleri kurar; masaüstüne kısayol koyar; programı açar.
# Zaten kuruluysa sadece günceller ve açar. Bu dosyada gizli bilgi yoktur.

set -u
REPO="dinjon4/MemecoinRadar"
DEST="${MR_DEST:-$HOME/MemecoinRadar}"   # MR_DEST / MR_NO_SHORTCUT / MR_NO_LAUNCH: sadece test için
TOOLS="${MR_TOOLS:-$HOME/.memecoinradar-araclar}"
PY_VERSION="3.14.8"
GH_FALLBACK="2.102.0"
TTY=/dev/tty   # "curl | bash" ile çalışırken klavye girişi buradan okunur

say()  { printf "\n\033[1;32m▶ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }
die()  { printf "\n\033[1;31m✖ %s\033[0m\n" "$*"; read -r -p "Kapatmak için Enter'a basın..." <"$TTY"; exit 1; }

# --- 1. Python (3.11 veya üstü) ---
find_python() {
    for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3 \
             /usr/local/bin/python3 "$(command -v python3 2>/dev/null)"; do
        [ -x "$p" ] || continue
        if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            echo "$p"; return 0
        fi
    done
    return 1
}

say "Python kontrol ediliyor"
PY="$(find_python)"
if [ -z "$PY" ]; then
    say "Python $PY_VERSION indiriliyor (python.org)"
    PKG="$(mktemp -d)/python.pkg"
    curl -fL --progress-bar -o "$PKG" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg" \
        || die "Python indirilemedi. İnternet bağlantınızı kontrol edin."
    warn "Açılan kurulum penceresinde 'Devam' ve 'Yükle'ye basın (Mac şifrenizi isteyebilir). Bitince pencereyi kapatın."
    open -W "$PKG"
    CERT="/Applications/Python ${PY_VERSION%.*}/Install Certificates.command"
    [ -f "$CERT" ] && bash "$CERT" >/dev/null 2>&1
    PY="$(find_python)" || die "Python kurulumu tamamlanmadı. Dosyayı tekrar çalıştırın."
fi
echo "Python: $("$PY" --version)"

# --- 2. git (Xcode komut satırı araçları) ---
say "git kontrol ediliyor"
if ! xcode-select -p >/dev/null 2>&1; then
    warn "Apple'ın komut satırı araçları gerekiyor. Açılan pencerede 'Yükle'ye basın (birkaç dakika sürebilir)."
    xcode-select --install >/dev/null 2>&1
    for _ in $(seq 1 180); do xcode-select -p >/dev/null 2>&1 && break; sleep 10; done
    xcode-select -p >/dev/null 2>&1 || die "Komut satırı araçları kurulmadı. Kurulum bitince bu dosyayı tekrar çalıştırın."
fi
echo "git: $(git --version)"

# --- 3. GitHub aracı (gh) ---
say "GitHub aracı (gh) kontrol ediliyor"
GH="$(command -v gh 2>/dev/null || true)"
[ -z "$GH" ] && [ -x "$TOOLS/gh/bin/gh" ] && GH="$TOOLS/gh/bin/gh"
if [ -z "$GH" ]; then
    ARCH="$(uname -m)"; [ "$ARCH" = "x86_64" ] && ARCH="amd64"
    VER="$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null \
           | sed -n 's/.*"tag_name": *"v\{0,1\}\([0-9.]*\)".*/\1/p' | head -1)"
    VER="${VER:-$GH_FALLBACK}"
    say "gh $VER indiriliyor"
    TMP="$(mktemp -d)"
    curl -fL --progress-bar -o "$TMP/gh.zip" \
        "https://github.com/cli/cli/releases/download/v$VER/gh_${VER}_macOS_${ARCH}.zip" || die "gh indirilemedi."
    unzip -q "$TMP/gh.zip" -d "$TMP" && rm -rf "$TOOLS/gh" && mkdir -p "$TOOLS" \
        && mv "$TMP/gh_${VER}_macOS_${ARCH}" "$TOOLS/gh" || die "gh açılamadı."
    GH="$TOOLS/gh/bin/gh"
fi
echo "gh: $("$GH" --version | head -1)"

# --- 4. GitHub'a giriş (bir kez) ---
if ! "$GH" auth status >/dev/null 2>&1; then
    say "GitHub'a giriş"
    warn "Birazdan bir kod ve tarayıcı açılacak. Sorulursa 'Authenticate Git with your GitHub credentials?' → Y."
    warn "Tarayıcıda GitHub hesabınızla giriş yapıp kodu girin ve 'Authorize' deyin."
    "$GH" auth login --web --git-protocol https --hostname github.com <"$TTY" || die "GitHub girişi tamamlanmadı."
fi
"$GH" auth setup-git >/dev/null 2>&1   # güncelleme butonu (git pull) bu girişi kullansın
"$GH" repo view "$REPO" >/dev/null 2>&1 \
    || die "GitHub hesabınızın '$REPO' deposuna erişimi yok. Depo sahibinin davetini e-postanızdan kabul edip tekrar deneyin."

# --- 5. Programı indir veya güncelle ---
if [ -d "$DEST/.git" ]; then
    say "Program zaten kurulu, güncelleniyor"
    git -C "$DEST" pull --ff-only || warn "Güncelleme yapılamadı; mevcut sürümle devam ediliyor."
else
    [ -e "$DEST" ] && die "$DEST klasörü var ama bir kurulum değil. Adını değiştirip tekrar deneyin."
    say "Program indiriliyor → $DEST"
    "$GH" repo clone "$REPO" "$DEST" -- --quiet || die "Program indirilemedi."
fi

# --- 6. Paketler ---
say "Paketler kuruluyor (ilk seferde birkaç dakika sürebilir)"
cd "$DEST" || die "Klasöre girilemedi."
[ -x .venv/bin/python ] || "$PY" -m venv .venv || die "Sanal ortam oluşturulamadı."
.venv/bin/python -m pip install -q --upgrade pip >/dev/null 2>&1
.venv/bin/python -m pip install -q -r requirements.txt || die "Paketler kurulamadı."

# --- 7. Masaüstü kısayolu ---
if [ -z "${MR_NO_SHORTCUT:-}" ]; then
    SHORTCUT="$HOME/Desktop/Memecoin Radar.command"
    printf '#!/bin/bash\nexec "%s/start.command"\n' "$DEST" > "$SHORTCUT" && chmod +x "$SHORTCUT"
fi

# --- 8. Başlat ---
say "Kurulum tamam: $(.venv/bin/python -c 'from radar import VERSION; print("v" + VERSION)')"
echo "Masaüstündeki 'Memecoin Radar' kısayoluyla açabilirsiniz."
echo "İlk açılışta panelde Ayarlar → Bağlantı anahtarları bölümünden kendi anahtarlarınızı girin."
[ -z "${MR_NO_LAUNCH:-}" ] && open "$DEST/start.command"
exit 0
