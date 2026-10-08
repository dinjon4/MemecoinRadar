# Geliştirme Günlüğü

Projede ne yapıldığının, hangi kararların neden alındığının ve neyin eksik kaldığının kaydı.
En yeni kayıt en üstte. Her çalışma oturumunun sonunda yeni bir kayıt eklenir.

- Plan: [memecoin-radar-plan.md](memecoin-radar-plan.md)
- Programın çalışma logu (bu dosyadan farklı): `logs/radar.log`

---

## 2026-10-08 — Paket 0.1

- `dist/MemecoinRadar-0.1-2026-10-08.zip` (75 KB): kod, ayarlar, belgeler, testler.
- Dışarıda bırakılanlar: `.env` (gizli anahtarlar), `.venv`, `data/` (veritabanı), `logs/`, `.git`, `.claude`.
- Boş klasöre açılıp sıfırdan kuruldu: paketler yüklendi, 34 test geçti.
- Kullanıcı isteğiyle tam paket de yapıldı: `dist/MemecoinRadar-0.1-2026-10-08-tam.zip` (264 KB) — veritabanı (SQLite `.backup` ile tutarlı kopya), loglar, `.git`, `.claude` dahil. `.env` güvenlik denetimi nedeniyle Claude tarafından eklenemedi; kullanıcı elle ekleyecek. `.venv` taşınabilir olmadığı için yok.
- O ana kadar: 209 token görüldü (19'u filtreyi geçiyor), 15 token için 476 büyük işlem / 264 cüzdan, günlük Helius ~890 kredi.

---

## 2026-10-08 — Aşama 2: Cüzdan akışı

**Durum:** Kod tamam, gerçek veriyle denendi. Kullanıcının panelde incelemesi bekleniyor.

**Yapılanlar**
- `radar/sources/helius.py`: Helius istemcisi. Her çağrının tahmini kredisi `api_usage` tablosuna yazılır. API anahtarı hata mesajlarına ve loglara sızmaz (testi var).
- `radar/flows.py`: havuzdaki büyük alım/satımları çeker, cüzdan ve token özetlerini üretir.
- Veritabanı: `trades`, `flow_state`, `wallet_balances`, `api_usage` tabloları; `tokens`'a `quote_mint`, `quote_price_usd` sütunları (eski veritabanına otomatik eklenir).
- Yeni ayarlar: `flow_interval_minutes` (15), `flow_max_tokens` (20), `helius_daily_credit_budget` (30.000).
- Panel: Tokenlar sayfasında satır seçince token detayı (whale net akış, cüzdan tablosu, Solscan linkleri); Durum sayfasında Helius günlük/aylık kredi.
- Terminal: `python main.py --token ADRES` ile tek tokenın cüzdan tablosu.
- Testler: 34 test, hepsi geçiyor (gerçek Helius işlemleriyle fixture dahil).

**Kararlar ve nedenleri**
- Enhanced Transactions API yerine `getTransactionsForAddress` kullanıldı: eski API bakım modunda ve istek başına 100 kredi; yenisi 100 işlem başına 10 kredi.
- Havuza **tutar filtresi** ile sadece büyük işlemler isteniyor. Aktif bir token dakikada ~100 işlem görebiliyor; filtresiz takip ayda ~2M kredi tutardı (kota 1M).
- Akış 3 dakikada değil 15 dakikada bir güncelleniyor (zaman ölçeği saatler).
- Alım/satım **havuzun bakiye değişiminden** okunuyor, cüzdanın SOL değişiminden değil: USDC ile ödeyen ve araya başka havuz giren alımlar da doğru yakalanıyor (gerçek örnekle doğrulandı).
- **Whale eşiği $5.000 → $1.500** (kullanıcı kararı). Ölçüm: 11 saatlik bir tokenda ≥$4.000 işlem 1, ≥$1.700 işlem 88.
- Helius'tan eşiğin %80'i üstü istenir (fiyat oynamasına pay), whale sayılması için tam eşik kullanılır.

**Bulgular**
- Filtre doğrulandı: aynı zaman aralığında filtreli/filtresiz karşılaştırmada hiçbir büyük işlem kaçmadı, fazladan işlem gelmedi.
- GOIF gibi bazı tokenlarda 24 saatte ~98 bin işlem var ama ortalama işlem ~$8: hacim botlarla şişirilmiş, büyük işlem yok.
- XRPN: 6 cüzdan, eşit miktardaki (1.994.978) tokenı aynı saniyede satıp havuzdan ~$860 bin çekmiş. Zincirden doğrulandı. Aşama 3'teki "bağlantılı cüzdan" kontrolünün yakalaması gereken örüntü.
- Maliyet: ilk tur (24 saatlik geçmiş dahil) 13 token ≈ 240 kredi. Sonraki turların ~150 kredi olması bekleniyor.

**Çalışma logundan gözlemler (2026-10-08 öğleden sonra)**
- Normal turda (geçmiş zaten çekilmişken) 13 token ≈ 170 kredi. Tahminle uyumlu.
- 14:10–15:48 arası hiç tarama yok: Mac uykudaydı (`pmset -g log` ile doğrulandı, 15:47:50'de uyandı). Program çökmüyor, uyanınca devam ediyor; ama uyurken izleme yok.

**Bilinen eksikler**
- **Mac uykuya geçince tarama duruyor.** Çözüm önerisi: `start.command`'da `caffeinate -i` (kapak kapanınca yine uyur) veya Aşama 7'de sunucu.
- Sadece PumpSwap destekleniyor (filtreyi geçenlerin ~%85'i). Meteora/Raydium havuzlarının kasaları havuz adresine ait değil; ayrı yöntem gerekir.
- SOL/USDC/USDT dışında bir tokenla eşleşmiş havuzlar atlanıyor (ör. CAPYBARA).
- Eşiğin altındaki işlemler cüzdan toplamlarına girmiyor.
- Gerçek günlük kredi kullanımı birkaç saat çalıştıktan sonra kontrol edilmeli.

---

## 2026-10-08 — Aşama 1: Yeni token tespiti

**Durum:** Tamam, kullanıcı test etti (tarama servisi gerçek veriyle çalıştı, panelde liste doldu).

**Yapılanlar**
- `radar/sources/geckoterminal.py`: keşif. `radar/sources/dexscreener.py`: likidite, MC, yaş.
- `radar/discovery.py`: filtreler (yaş, likidite, bonding curve) ve kayıt. Elenenler sebebiyle birlikte saklanır.
- `radar/http.py`: adres başına istek aralığı (GeckoTerminal 6 sn), 429/5xx'te bekleyip tekrar deneme, User-Agent.
- Panel: Tokenlar sayfası (arama, elenenleri gösterme, DexScreener linki).
- `python main.py --once` terminalde tablo basar.

**Kararlar ve nedenleri**
- GeckoTerminal `/new_pools` tek başına yetmiyor: 20 havuz ≈ 20 saniye, %80+ bonding curve. Her taramada 5 liste okunuyor (trend 1s/6s, işlem sayısı, hacim, yeni). Token "ilgi görmeye başladığında" yakalanıyor; zaman ölçeği saatler olduğu için yeterli.
- Likidite ve yaş DexScreener'dan (30 token/istek, geniş limit). Token yaşı = en eski havuzunun açılışı.

**Bulgular**
- GeckoTerminal ücretsiz limiti belgelenenden sıkı (~2,5 sn aralıkla 429).
- DexScreener User-Agent'sız isteklere 403 veriyor.
- Yüksek hacimli genç havuzların çoğunun likiditesi sıfır (boşaltılmış / sahte hacim). Likidite filtresi şart.
- DEX adları kaynağa göre değişiyor (`pump-fun`/`pumpfun`, `meteora-dbc`/`meteoradbc`, `bags`); bonding curve listesi `radar/sources/__init__.py`.
- Aynı isimle kopya tokenlar var (iki "SharkTank"). Aşama 3'te ele alınacak.

**Bilinen eksikler**
- Hiç ilgi görmeyen yeni tokenlar kaçar.
- 24 saatten eski kayıtlar silinmiyor (Aşama 5 takibi için tutuluyor).

---

## 2026-10-08 — Aşama 0: Kurulum

**Durum:** Tamam, kullanıcı test etti (Telegram'a "Merhaba" geldi, panel açıldı).

**Yapılanlar**
- Proje iskeleti, git, sanal ortam (Python 3.14), `requirements.txt` (sürümler sabit, Windows için `tzdata`).
- `radar/config.py`: tüm ayarlar tek listede (`SETTINGS`); açılışta doğrulama, Türkçe hata mesajları, açıklamalı `config.yaml` üretimi.
- Loglama (`logs/radar.log`, dönen dosya), Telegram gönderimi (deneme modu, her mesajda "yatırım tavsiyesi değildir").
- Yerel panel (Streamlit, sadece 127.0.0.1): Durum ve Ayarlar sayfaları.
- `start.command` (Mac) / `start.bat` (Windows), README.
- `python main.py --find-chat-id`, `--test-telegram`.

**Kurulum sırasında çözülenler**
- Mac'teki Xcode lisansı / eski Python 3.9 → python.org'dan Python 3.14 kuruldu.
- python.org Python'unda SSL sertifikaları eksikti → `Install Certificates.command` çalıştırıldı.
- Telegram chat ID'si bulunamadı → kullanıcı mesajı yanlış bota yazmıştı; `getMe` ile doğru bot gösterildi.

**Bilinen eksikler**
- `start.bat` Windows'ta hiç denenmedi.
- Henüz git commit'i yapılmadı.
