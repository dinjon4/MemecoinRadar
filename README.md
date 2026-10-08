# Memecoin Radar

Solana'da yeni çıkan memecoinleri izleyip Telegram'a uyarı gönderen program.
**Sadece izleme yapar.** Alım-satım yapmaz, cüzdan şifresi/private key istemez. Uyarılar yatırım tavsiyesi değildir.

Proje planı: [memecoin-radar-plan.md](memecoin-radar-plan.md)

## İlk kurulum

### 1. Python
[python.org](https://www.python.org/downloads/) adresinden Python 3.12 veya daha yenisini kurun.
- **Mac:** Kurulumdan sonra *Uygulamalar → Python 3.x* klasöründeki **Install Certificates.command** dosyasına çift tıklayın.
- **Windows:** Kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin.

### 2. Programı ilk kez başlatma
- **Mac:** `start.command` dosyasına çift tıklayın (Mac uyarı verirse: sağ tık → *Aç*).
- **Windows:** `start.bat` dosyasına çift tıklayın.

İlk açılışta gerekli paketler kurulur (birkaç dakika). Sonra panel tarayıcıda açılır.

### 3. Telegram bot'u oluşturma
1. Telegram'da **@BotFather** hesabını açın ve `/newbot` yazın.
2. Bot'a bir isim, sonra sonu `bot` ile biten bir kullanıcı adı verin (ör. `benim_radar_bot`).
3. BotFather size `123456789:ABC...` gibi bir **token** verir. Bunu kimseyle paylaşmayın.
4. Telegram'da yeni bot'unuzu bulun ve ona herhangi bir mesaj yazın (ör. "merhaba").

### 4. Anahtarları panelden girme
Panelde **Ayarlar → Bağlantı anahtarları** bölümüne gidin:
1. **Telegram bot token**: BotFather'ın verdiği token'ı yapıştırıp *Kaydet*. Panel önce token'ı dener; doğruysa bot'un adını gösterir.
2. **Telegram chat ID**: *Chat ID'mi bilmiyorum* → *Bot'a yazanları bul* → kendi adınızın yanındaki *Bunu kullan*.
3. **Helius API anahtarı**: [dashboard.helius.dev](https://dashboard.helius.dev) → ücretsiz hesap → *API Keys*. Anahtarı yapıştırıp *Kaydet*.

Anahtarlar işletim sisteminin şifreli kasasında saklanır (Mac: Anahtar Zinciri, Windows: Kimlik Bilgisi Yöneticisi).
Hiçbir proje dosyasında durmaz, panelde gösterilmez; proje klasörünü kopyalasanız veya paketleseniz de gitmez.
Yeni bir bilgisayarda panelden bir kez daha girilir.

### 5. Test mesajı
**Ayarlar → Telegram testi → Test mesajı gönder.** Telegram'a "Merhaba!" mesajı gelmeli.

## Arkadaşlar için kurulum (GitHub'dan)
Program gizli bir GitHub deposunda durur. Bir kez kurulur; sonrası panelden **Güncelle** butonuyla.

1. **GitHub hesabı:** Hesabınız yoksa [github.com](https://github.com)'dan ücretsiz açın. Depo sahibi sizi davet eder; e-postanızdaki daveti kabul edin.
2. **Python:** Yukarıdaki "1. Python" adımı.
3. **GitHub aracı (gh):** [cli.github.com](https://cli.github.com)'dan Mac için `.pkg`, Windows için `.msi` kurulum dosyasını indirip kurun.
   **Windows'ta ayrıca** [git-scm.com](https://git-scm.com/download/win)'dan "Git for Windows"u kurun (Mac'te git zaten var).
4. **GitHub'a giriş (bir kez):** Terminal (Windows: Komut İstemi) açıp yazın:
   ```
   gh auth login
   ```
   Sorulara: `GitHub.com` → `HTTPS` → "Authenticate Git with your GitHub credentials?" **Yes** → `Login with a web browser`. Tarayıcıda onaylayın.
5. **Programı indirme:** Programın duracağı klasöre geçip (ör. `cd Desktop`) yazın:
   ```
   gh repo clone DEPO_SAHIBI/MemecoinRadar
   ```
6. **Başlatma:** `MemecoinRadar` klasöründeki `start.command` (Mac) veya `start.bat` (Windows) dosyasına çift tıklayın.
7. **Kendi anahtarlarınız:** Panel → Ayarlar → Bağlantı anahtarları. Herkes **kendi** Telegram bot'unu ve **kendi** ücretsiz Helius anahtarını kullanmalı (aynı Helius anahtarı paylaşılırsa aylık kota birkaç kat hızlı biter).

### Güncelleme
Yeni sürüm çıkınca panelin sol menüsünde **🔔 Yeni sürüm var** yazar. **Sistem → Güncelle**'ye basın:
program yeni sürümü indirir, gerekirse yeni paketleri kurar ve kendini yeniden başlatır.
Ayarlarınız (`config.yaml`), anahtarlarınız ve verileriniz güncellemeden etkilenmez.
Program dosyalarını elle değiştirmeyin; değiştirilmişse güncelleme onları ezmemek için durur.

## Günlük kullanım
- **Mac:** `start.command` dosyasına çift tıklayın. (İlk seferde Mac uyarı verirse: sağ tık → *Aç*.)
- **Windows:** `start.bat` dosyasına çift tıklayın.

Tarama servisi başlar ve panel tarayıcıda açılır (`http://127.0.0.1:8501`). Panel sadece bu bilgisayardan açılabilir.

**Mac:** Terminal penceresi açık kaldığı sürece Mac kendiliğinden uykuya geçmez, tarama kesintisiz devam eder.
Ekran yine kararabilir. Kapağı kapatırsanız Mac yine uyur ve tarama durur.

**Durdurmak için:** Terminal penceresinde **Ctrl+C** basın veya pencereyi kapatın (Mac "çalışan işlem sonlandırılsın mı?" diye sorarsa *Sonlandır*).
Tarama, panel ve uyku engeli birlikte kapanır; Mac normal uyku ayarına döner.
Windows'ta iki pencereyi de kapatın.

## Sorun giderme
- Panelin **Sistem** sayfasında son log kayıtları ve API kullanımı görünür; **Genel Bakış** sayfası özet verir. Ayrıntılı kayıtlar `logs/radar.log` dosyasındadır.
- Ayarlar panelin **Ayarlar** sayfasından değiştirilir (ya da `config.yaml` elle düzenlenir).
- Testleri çalıştırmak için: `.venv/bin/python -m unittest` (Windows: `.venv\Scripts\python -m unittest`)
