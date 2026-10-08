# Memecoin Radar

Solana'da yeni çıkan memecoinleri izleyip Telegram'a uyarı gönderen program.
**Sadece izleme yapar.** Alım-satım yapmaz, cüzdan şifresi/private key istemez. Uyarılar yatırım tavsiyesi değildir.

Proje planı: [memecoin-radar-plan.md](memecoin-radar-plan.md)

## İlk kurulum

### 1. Python
[python.org](https://www.python.org/downloads/) adresinden Python 3.12 veya daha yenisini kurun.
- **Mac:** Kurulumdan sonra *Uygulamalar → Python 3.x* klasöründeki **Install Certificates.command** dosyasına çift tıklayın.
- **Windows:** Kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin.

### 2. Telegram bot'u oluşturma
1. Telegram'da **@BotFather** hesabını açın ve `/newbot` yazın.
2. Bot'a bir isim, sonra sonu `bot` ile biten bir kullanıcı adı verin (ör. `benim_radar_bot`).
3. BotFather size `123456789:ABC...` gibi bir **token** verir. Bunu kimseyle paylaşmayın.
4. Proje klasöründeki `.env.example` dosyasını kopyalayıp adını `.env` yapın.
   - Mac'te Finder nokta ile başlayan dosyaları gizler: Finder'da **Cmd + Shift + .** ile görünür yapın.
5. `.env` dosyasını bir metin düzenleyiciyle açın, token'ı `TELEGRAM_BOT_TOKEN=` satırının sonuna yapıştırıp kaydedin.
6. Telegram'da yeni bot'unuzu bulun ve ona herhangi bir mesaj yazın (ör. "merhaba").

### 3. Chat ID'yi bulma
Proje klasöründe bir terminal açın:
- **Mac:** Finder'da klasöre sağ tık → *Hizmetler → Klasörde Yeni Terminal*
- **Windows:** Klasörde adres çubuğuna `cmd` yazıp Enter

İlk seferde sanal ortamı kurun:

| Mac | Windows |
|---|---|
| `python3 -m venv .venv` | `py -m venv .venv` |
| `.venv/bin/pip install -r requirements.txt` | `.venv\Scripts\pip install -r requirements.txt` |

Sonra chat ID'yi bulun:

| Mac | Windows |
|---|---|
| `.venv/bin/python main.py --find-chat-id` | `.venv\Scripts\python main.py --find-chat-id` |

Çıkan numarayı `.env` içindeki `TELEGRAM_CHAT_ID=` satırına yazıp kaydedin.

### 4. Test mesajı

| Mac | Windows |
|---|---|
| `.venv/bin/python main.py --test-telegram` | `.venv\Scripts\python main.py --test-telegram` |

Telegram'a "Merhaba!" mesajı gelmeli.

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
- Panelin **Durum** sayfasında son log kayıtları görünür. Ayrıntılı kayıtlar `logs/radar.log` dosyasındadır.
- Ayarlar panelin **Ayarlar** sayfasından değiştirilir (ya da `config.yaml` elle düzenlenir).
- Testleri çalıştırmak için: `.venv/bin/python -m unittest` (Windows: `.venv\Scripts\python -m unittest`)
