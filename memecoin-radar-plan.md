# Memecoin Radar — Proje Planı (Claude Code için)

## Claude Code'a not
Bu dosya projenin tek kaynağıdır. Her aşamaya başlamadan önce bu dosyayı ve `GELISTIRME_GUNLUGU.md`'yi oku.
- Her çalışma oturumunun sonunda `GELISTIRME_GUNLUGU.md`'nin en üstüne kayıt ekle (yapılanlar, kararlar, bulgular, eksikler).
- Kullanıcı beginner–mid seviye bir yatırımcı, yazılımcı değil. Kurulum ve çalıştırma adımlarını sade, adım adım anlat.
- Aşama aşama ilerle. Bir aşama bitip kullanıcı test etmeden sonrakine geçme.
- Her aşama sonunda: neyin çalıştığını, nasıl test edileceğini ve bilinen eksikleri kısaca yaz.
- API limitleri ve fiyatları değişebilir. Kullanmadan önce güncel dokümantasyonu kontrol et.
- Bir aşamada plandan sapmak gerekirse (ör. bir API beklendiği gibi çalışmıyorsa) bu dosyayı güncelle ve kullanıcıya söyle.

## Amaç
Solana'da yeni çıkan memecoinleri izleyen, büyük cüzdanların para akışını ve riskleri özetleyip **Telegram'a uyarı** gönderen bir program.
İkinci katman olarak haber/hikâye akışı ile yeni tokenları eşleştirmek.

**Bu program sadece izleme yapar.**
- Otomatik alım-satım YOK.
- Cüzdan private key / seed phrase ASLA istenmez, saklanmaz, kodda yer almaz.
- Uyarılar yatırım tavsiyesi değildir. Her Telegram mesajının sonunda kısa bir "yatırım tavsiyesi değildir" notu olsun.

## Kullanıcı tercihleri
| Konu | Karar |
|---|---|
| Ana hedef | Önce cüzdan takibi, sonra haber/hikâye katmanı |
| Arayüz | Uyarılar: Telegram (Türkçe). Yönetim ve inceleme: tarayıcıda açılan yerel panel (sadece bu bilgisayardan erişilir) |
| Platform | Mac ve Windows'ta aynı şekilde çalışmalı |
| Bütçe | Ücretsiz başla (ücretsiz planlar / açık API'ler) |
| Otomasyon | Sadece izleme |
| Whale eşiği | Ayarlanabilir, varsayılan $1.500 (Aşama 2 ölçümüne göre $5.000 bu piyasada çok nadirdi) |
| Zaman ölçeği | Saatler (dakika düzeyi hız gerekmez) |
| Çalışma yeri | Önce kendi bilgisayarı; sonra istenirse ucuz bulut sunucu |
| Zincir | Solana |

## Temel yaklaşım
- **Önce ele, sonra puanla.** Ciddi risk bulguları (bkz. Aşama 3) tokenı doğrudan eler (veto). Skor sadece eleği geçen tokenları sıralar. Programın en güvenilir kullanımı kötü tokenları elemektir.
- **Ucuzdan pahalıya kontrol.** Önce ucuz kontroller (likidite, yaş, mint/freeze authority), sadece bunları geçenlere pahalı kontroller (işlem geçmişi, cüzdan analizi). Ücretsiz limitler böyle korunur.
- **Ölç, sonra ayarla.** Skor ağırlıkları tahminle başlar, Aşama 5 verisiyle ayarlanır.

## Teknik tercihler (basit tut)
- Dil: Python
- Veritabanı: SQLite (tek dosya, kurulum gerektirmez)
- Ayarlar: `config.yaml` (eşikler, aralıklar, açık/kapalı özellikler). Program açılırken ayarlar kontrol edilsin; hatalı/eksik değer varsa anlaşılır bir hata mesajı versin.
- Gizli anahtarlar: `.env` dosyası (API key, Telegram bot token, chat ID). `.gitignore`'a ekle.
- Versiyon kontrolü: git (Aşama 0'da `git init`).
- **Platform bağımsızlığı (Mac + Windows):**
  - Dosya yolları `pathlib` ile; elle `/` veya `\` yazılmaz.
  - Tüm dosyalar UTF-8 ile açılır/yazılır (Türkçe karakter ve emoji sorunu olmasın).
  - Sadece bir işletim sistemine özgü araç/komut kullanılmaz; kaçınılmazsa her iki platformun karşılığı yazılır.
  - Kurulum ve çalıştırma talimatları her adımda hem Mac hem Windows için verilir (sanal ortam aktivasyonu farklıdır).
  - Kolay başlatma için iki dosya: `start.command` (Mac) ve `start.bat` (Windows). Tarama servisini ve paneli birlikte başlatır, paneli tarayıcıda açar.
- **Yerel panel (tarayıcı arayüzü):**
  - Streamlit ile yapılır (sadece Python, ayrı web bilgisi gerekmez).
  - Sadece `127.0.0.1` adresinde dinler; ağdaki başka cihazlar veya internet erişemez. Bu yüzden giriş/şifre gerekmez.
  - Tarama servisi (`main.py`) ve panel **ayrı süreçlerdir**; panel kapansa da tarama devam eder. İkisi SQLite ve `config.yaml` üzerinden haberleşir.
  - Panelden ayar değiştirilince tarama servisi bir sonraki taramada yeni ayarları okur (yeniden başlatma gerekmez). Kaydetmeden önce değerler doğrulanır.
  - API anahtarları panelde gösterilmez; `.env` panelden düzenlenmez.
- Zaman: Veritabanında her şey UTC saklanır; Telegram mesajlarında Türkiye saati gösterilir.
- Loglama: Hem terminale hem `logs/` klasöründe dönen (rotating) bir log dosyasına yaz. API hataları, limit aşımları, gönderilen uyarılar loglansın.
- HTTP istekleri: Her istekte belirgin bir `User-Agent` başlığı gönder (ör. `MemecoinRadar/0.1`). DexScreener başlıksız isteklere 403 veriyor (2026-10-08'de görüldü).
- Hata dayanıklılığı: API çağrılarında zaman aşımı, 429 (limit aşımı) ve 5xx hatalarında bekleyip tekrar deneme (exponential backoff). Tek bir tokenın hatası taramanın tamamını durdurmasın.
- Veri kaynakları (ücretsiz başlangıç — kullanmadan önce güncel dokümanı doğrula):
  - **Yeni token keşfi:** GeckoTerminal API. Aşama 1'de doğrulananlar (2026-10-08):
    - `/new_pools` çok hızlı akıyor: 20 havuz ≈ 20 saniye, %80+ Pump.fun bonding curve. Tek başına yetmez.
    - Bu yüzden her taramada 5 liste okunur: trend (1s, 6s), işlem sayısına göre, hacme göre, yeni havuzlar. Zaman ölçeğimiz saatler olduğu için tokenı "ilgi görmeye başladığında" yakalamak yeterli.
    - Ücretsiz limit belgelenenden sıkı (~2,5 sn aralıkla 429). İstekler arası 6 sn beklenir; keşif ~30 sn sürer.
    - Yüksek hacimli genç havuzların çoğu likiditesi sıfır (boşaltılmış / sahte hacim) tokenlar. Likidite filtresi şart; likidite DexScreener'dan alınır.
    - İleride daha fazla kapsama gerekirse: PumpPortal "migration" akışı (Pump.fun mezuniyetleri).
  - **Fiyat / MC / likidite / yaş:** DexScreener `/tokens/v1/solana/{adresler}` (istek başına 30 token). Token yaşı = en eski havuzunun açılışı. Takip edilen tüm genç tokenlar her taramada buradan güncellenir.
  - **DEX adları kaynağa göre değişir:** GeckoTerminal `pump-fun`/`meteora-dbc`, DexScreener `pumpfun`/`meteoradbc`/`bags`. Bonding curve listesi `radar/sources/__init__.py` içinde.
  - **Risk kontrolleri:** RugCheck.xyz API (ücretsiz) + doğrudan RPC ile mint/freeze authority kontrolü.
  - **Cüzdan ve işlem detayları:** Helius ücretsiz plan (ayda 1M kredi, 10 istek/sn). Aşama 2'de doğrulananlar (2026-10-08):
    - Enhanced Transactions API eskidi (bakım modunda, istek başına 100 kredi) — kullanılmıyor.
    - `getTransactionsForAddress` (full) ücretsiz planda açık: 100 işlem başına 10 kredi, çağrı başına en az 10. `maxSupportedTransactionVersion: 1` şart.
    - Havuz adresine `tokenTransfer` tutar filtresi uygulanınca sadece büyük alım/satımlar gelir (doğrulandı: hiçbirini kaçırmıyor, fazladan getirmiyor). Aktif bir token dakikada ~100 işlem görebildiği için filtresiz takip kotayı aşardı.
    - Alım/satım havuzun bakiye değişiminden okunur (havuza SOL girip token çıkıyorsa alım). Cüzdan USDC ile ödeyip araya başka havuz girse de doğru çalışır.
    - Bu yöntem sadece kasaları havuz adresine ait DEX'lerde çalışır: şimdilik **PumpSwap** (filtreyi geçenlerin ~%85'i). Meteora/Raydium sonra eklenebilir.
    - Gerçek tur maliyeti: 11 token ≈ 120 kredi.
    - **Whale eşiği bulgusu:** MC'si yüz binler seviyesindeki memecoinlerde $5.000+ işlem çok nadir (11 saatlik bir tokenda ≥$4.000: 1, ≥$1.700: 88). Varsayılan $1.500 yapıldı (kullanıcı kararı).
  - **SOL/USD fiyatı:** Her taramada bir kez çek (whale eşiği dolar cinsinden olduğu için).
  - **Telegram:** Bot API (ücretsiz).
- Saatlik zaman ölçeği yüzünden canlı akış yerine **periyodik tarama** yeterli.
- **Limit bütçesi:** Aşama 2'ye başlamadan önce "tarama başına kaç API çağrısı × günde kaç tarama" hesabı yap ve Helius ücretsiz kotasıyla karşılaştır. Her token için en son okunan işlem imzasını sakla, sonraki taramada sadece yeni işlemleri çek.

## Önerilen klasör yapısı
```
MemecoinRadar/
  main.py              # tarama servisi (döngü)
  panel.py             # yerel Streamlit paneli
  start.command        # Mac: tek tıkla başlat
  start.bat            # Windows: tek tıkla başlat
  config.yaml
  .env / .env.example
  radar/
    sources/           # geckoterminal, dexscreener, helius, rugcheck istemcileri
    discovery.py       # Aşama 1
    flows.py           # Aşama 2
    risk.py            # Aşama 3
    scoring.py         # Aşama 4
    notify.py          # Telegram
    tracking.py        # Aşama 5
    db.py
  data/
    radar.db
    cex_wallets.txt    # bilinen borsa cüzdanları (bağlantılı cüzdan analizinde hariç tutulur)
  logs/
  tests/
    fixtures/          # kaydedilmiş örnek API cevapları (internetsiz test için)
```

## Ayarlar (config.yaml taslağı)
```yaml
# Tarama
scan_interval_minutes: 3     # tarama sıklığı
token_max_age_hours: 24      # sadece bu kadar yeni tokenlar
min_liquidity_usd: 10000     # altındakileri ele
include_bonding_curve: false # Pump.fun'da henüz havuza geçmemiş tokenlar dahil mi

# Cüzdan akışı
whale_min_usd: 1500          # büyük işlem eşiği

# Risk
top10_holder_warn_pct: 40    # ilk 10 cüzdan (havuz/burn hariç) arzın %'sinden fazlasını tutuyorsa uyar
dev_sold_veto_pct: 50        # dev arzındaki payının bu %'sinden fazlasını sattıysa ele
veto_if_mint_authority: true # mint authority iptal edilmemişse ele
veto_if_freeze_authority: true

# Skor ve uyarı
min_score_to_alert: 60       # bu skorun altı Telegram'a gitmez
score_weights:               # toplam 100; Aşama 5 verisiyle ayarlanacak
  whale_net_flow: 50
  buyer_diversity: 30
  liquidity_to_mc: 20
alert_cooldown_hours: 6      # aynı token için bekleme süresi
realert_score_jump: 15       # skor bu kadar artarsa bekleme süresi beklenmeden tekrar uyar

# Çalışma
dry_run: false               # true ise Telegram'a göndermez, sadece terminale yazar
heartbeat_hours: 24          # "program çalışıyor" özet mesajı sıklığı (0 = kapalı)
```

## Aşamalar

### Aşama 0 — Kurulum
- Proje klasörü, `git init`, sanal ortam, `requirements.txt`, `.env.example`, `config.yaml`, `.gitignore`
- Loglama ve config doğrulamasının temeli
- Telegram bot oluşturma ve chat ID bulma adımlarını kullanıcıya sade anlat
- Panelin iskeleti: **Durum** sayfası (tarama servisi çalışıyor mu, son tarama zamanı, son log satırları) ve **Ayarlar** sayfası (`config.yaml` değerlerini form ile düzenle, doğrula, kaydet)
- `start.command` / `start.bat` başlatma dosyaları
- Test: "Merhaba" mesajı Telegram'a düşmeli; `dry_run: true` iken mesaj sadece terminalde görünmeli; panel tarayıcıda açılmalı ve bir ayar değişikliği `config.yaml`'a yazılmalı. Mac'te ve (mümkünse) Windows'ta denenmeli.

### Aşama 1 — Yeni token tespiti
- Önce veri kaynağını doğrula: GeckoTerminal `new_pools` gerçekten son X saatin Solana havuzlarını veriyor mu, limitleri ne?
- Son X saatte çıkan Solana tokenlarını bul (GeckoTerminal ile keşif, DexScreener ile detay)
- Likidite ve yaş filtresini uygula; `include_bonding_curve` ayarına uy
- Veritabanına kaydet (adres, isim, sembol, çıkış zamanı, MC, likidite, havuz adresi, DEX)
- Aynı token tekrar görülürse yeni kayıt açma, güncelle
- Panel: **Tokenlar** sayfası (tablo: isim, sembol, yaş, MC, likidite, DexScreener linki; sıralama ve filtre)
- Test: Terminalde ve panelde yeni tokenların listesi görünmeli

### Aşama 2 — Cüzdan akışı
Sadece Aşama 1 ve Aşama 3'ün ucuz kontrollerini geçen tokenlar için:
- Alım/satım işlemlerini çek (en son okunan imzadan itibaren), SOL tutarını SOL/USD fiyatıyla dolara çevir, eşiğin üstündekileri "whale" olarak işaretle
- Cüzdan başına: toplam alım, toplam satım, net akış, kalan token, ilk alım zamanı
- Token başına: toplam whale net akışı (giriş mi çıkış mı), farklı alıcı sayısı
- Panel: Tokenlar sayfasında bir tokena tıklayınca **token detayı** (cüzdan tablosu, whale işlemleri)
- Test: Tek bir token için cüzdan tablosu terminalde ve panelde görünmeli; ikinci taramada sadece yeni işlemler çekilmeli (loglardan kontrol)

### Aşama 3 — Risk kontrolleri
Her kontrol için evet/hayır + kısa açıklama. **Veto** olanlar tokenı skordan bağımsız eler.

Ucuz kontroller (Aşama 2'den önce çalışır):
- **Mint authority** iptal edilmiş mi? Edilmediyse dev yeni token basabilir. → Veto
- **Freeze authority** iptal edilmiş mi? Edilmediyse tokenlar dondurulabilir (honeypot). → Veto
- **Likidite:** Havuzdaki miktar, LP yakılmış/kilitli mi (Pump.fun'dan geçen havuzlarda LP genelde otomatik yakılır)
- **RugCheck sonucu:** Varsa risk özetini kaydet, kendi kontrollerimizle karşılaştır

Pahalı kontroller (Aşama 2 verisiyle):
- **Creator/dev satışı:** Tokenı oluşturan cüzdan sattı mı, ne kadarını. `dev_sold_veto_pct` üstü → Veto
- **Holder yoğunluğu:** İlk 10 cüzdanın arzdaki payı. Havuz/bonding curve hesabı, burn adresi ve bilinen kilit kontratları hesaba **katılmaz**.
- **Bağlantılı cüzdanlar:** Aynı kaynaktan SOL almış cüzdanları grupla, tek kişi say.
  - `data/cex_wallets.txt` içindeki borsa cüzdanlarından fonlananlar gruplanmaz (yoksa alakasız yüzlerce cüzdan "tek kişi" sayılır).
  - Bu bir tahmindir; mesajda "olası grup" diye yazılır.

- Panel: Token detayına risk kontrolleri (✅/⚠️/⛔ + açıklama); Tokenlar sayfasında elenenler ve eleme sebebi görülebilsin
- Test: Bilinen birkaç token için (biri temiz, biri mint authority açık vb.) her kontrolün sonucu terminalde ve panelde görünmeli

### Aşama 4 — Skor ve Telegram uyarısı
- Önce veto kontrolü: veto varsa skor hesaplanmaz, uyarı gitmez (log'a sebebiyle yazılır)
- 0–100 basit skor, ağırlıklar `config.yaml`'dan: whale net akışı (+), alıcı çeşitliliği (+), likidite/MC oranı (+), uyarı seviyesindeki risk bulguları (−)
- "Holder artışı" ilk sürümde yok (zaman içinde holder sayısı tutmak pahalı); gerekirse Aşama 5 sonrası eklenir
- Mesajda neden o skoru aldığı yazsın
- Aynı token için tekrar tekrar uyarı atma (`alert_cooldown_hours`); skor `realert_score_jump` kadar artarsa tekrar uyar
- Telegram mesajlarında özel karakterleri doğru kaçır (token isimleri bozuk karakter içerebilir)
- Mesaj örneği:
```
🟢 $TOKEN — Skor 72/100
MC: $85K | Likidite: $22K | Yaş: 3 saat
Whale net akış: +$31K (5 cüzdan, olası 2 grup)
⚠️ İlk 10 cüzdan arzın %46'sı
✅ Dev satış yapmadı | ✅ Mint/freeze kapalı
Link: dexscreener...
Yatırım tavsiyesi değildir.
```
- Heartbeat: `heartbeat_hours` aralıkla "çalışıyorum: X token tarandı, Y elendi, Z uyarı" mesajı. Program art arda hata alıyorsa Telegram'a hata uyarısı.
- Panel: **Uyarılar** sayfası (gönderilen uyarıların geçmişi, skor ve skor dökümü); token detayında skorun nasıl hesaplandığı; ayarlar sayfasında "test mesajı gönder" butonu
- Test: Gerçek bir token için mesaj Telegram'a düşmeli ve panelde uyarı geçmişinde görünmeli; aynı token bir sonraki taramada tekrar mesaj atmamalı

### Aşama 5 — Takip ve günlük
- Uyarı verilen tokenların 1, 6 ve 24 saat sonraki durumunu (fiyat, MC, likidite) kaydet
- **Karşılaştırma grubu:** Uyarı verilmeyen tokenlardan (düşük skorlu ve elenenler) rastgele bir kısmını da aynı şekilde takip et. Böylece "uyarılar rastgele tokenlardan daha mı iyi?" sorusu cevaplanabilir.
- "Yükseldi" / "çöktü" tanımı config'de olsun (ör. 24 saatte +%50 / −%70 veya likidite sıfırlandı)
- Haftalık basit özet (Telegram): kaç uyarı, kaçı yükseldi, kaçı çöktü; aynı oranlar karşılaştırma grubu için; en çok hangi veto sebebi çalıştı
- Panel: **Performans** sayfası (uyarılar vs. karşılaştırma grubu; skor aralığına göre sonuçlar; basit grafikler)
- Amaç: skorun gerçekten işe yarayıp yaramadığını görmek. Skor ayarı bu verilere göre yapılır.

### Aşama 6 — Haber / hikâye katmanı (sonraki adım)
- Ücretsiz kaynaklarla başla: haber RSS akışları (ör. Google News RSS, kripto haber siteleri), mümkünse Reddit (API artık uygulama kaydı istiyor; güncel koşulları kontrol et)
- X (Twitter) verisi ücretli; sonradan bütçe olursa eklenir
- Basit yöntem: başlıklardaki anahtar kelimeleri yeni token isim/sembolleriyle eşleştir
  - Çok yaygın kelimeler (CAT, DOG, AI, TRUMP, MOON vb.) için yasaklı kelime listesi ve minimum kelime uzunluğu kullan; yoksa her token bir haberle "eşleşir"
  - Haber, tokenın çıkışından önceki birkaç saat içinde olmalı
- Gelişmiş yöntem (sonra): anlam benzerliği ile eşleştirme
- Eşleşme varsa Telegram mesajına "Hikâye: ..." satırı ekle (kaynak linkiyle)

### Aşama 7 — 7/24 çalıştırma (isteğe bağlı)
- Bu aşamaya kadar kendi bilgisayarında: bilgisayar uykuya geçince program durur. Mac'te `caffeinate`, Windows'ta güç ayarları ile uykuyu engellemeyi anlat.
- Sunucuda panel internete açılmaz; sunucuya SSH tüneli ile bağlanıp yine `127.0.0.1` üzerinden açılır.
- Ucuz bir bulut sunucuya taşıma adımları
- Çökünce kendini yeniden başlatma (systemd veya benzeri)
- Veritabanı yedeği (günlük kopya)

### Ek (sonra) — Telegram komutları
- `/token ADRES` → o token için anlık analiz (Aşama 4'ten sonra eklenmesi kolay)
- `/durum` → son tarama zamanı, kaç token izleniyor
- Ayar değiştirme asıl olarak panelden yapılır; Telegram'dan ayar komutları (ör. `/esik 10000`) sadece bilgisayar başında değilken lazım olursa eklenir
- Komutlar **sadece** `.env`'deki chat ID'den gelirse kabul edilir

## Test yaklaşımı
- Her veri kaynağı için birkaç gerçek API cevabını `tests/fixtures/` altına kaydet. Ayrıştırma, risk ve skor kodu internetsiz bu dosyalarla test edilsin (API limitini harcamaz, sonuç tekrarlanabilir).
- Yeni bir aşama eskisini bozmasın diye basit testler aşama aşama eklensin.

## Bilinen sınırlar (kullanıcı bilsin)
- Birçok "whale" aslında insider veya bottur. Program bunu tahmin eder, kesin bilemez.
- Aynı kişi kendi cüzdanları arasında işlem yaparak sahte hacim/birikim gösterebilir.
- Bağlantılı cüzdan tespiti tahmindir; borsadan fonlanan veya ara cüzdanlarla dağıtılan cüzdanlar yakalanamaz.
- Ücretsiz veri gecikmeli ve limitlidir. Uyarı geldiğinde fiyat hareket etmiş olabilir.
- Temiz görünen bir token da çökebilir; risk kontrolleri sadece bilinen kötü kalıpları yakalar.
- En güvenilir kullanımı: kötü tokenları elemek (risk filtresi), "kesin kazanç" bulmak değil.

## Açık sorular (sonra karar verilecek)
- Skor ağırlıkları: başlangıç config'deki gibi; Aşama 5 verisi gelince güncellenecek.
- Pump.fun bonding curve aşamasındaki tokenlar dahil edilsin mi? (Varsayılan: hayır)
- Hangi haber kaynakları takip edilsin?
- Haftalık özet hangi gün/saatte gelsin?
