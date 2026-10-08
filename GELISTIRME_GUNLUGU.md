# Geliştirme Günlüğü

Projede ne yapıldığının, hangi kararların neden alındığının ve neyin eksik kaldığının kaydı.
En yeni kayıt en üstte. Her çalışma oturumunun sonunda yeni bir kayıt eklenir.

- Plan: [memecoin-radar-plan.md](memecoin-radar-plan.md)
- Programın çalışma logu (bu dosyadan farklı): `logs/radar.log`

---

## 2026-10-08 — GitHub'a yüklendi

- Kullanıcı onayıyla `gh` Homebrew ile kuruldu; kullanıcı `gh auth login` ile kendisi giriş yaptı (hesap: dinjon4).
- Gizli depo oluşturuldu ve yüklendi: https://github.com/dinjon4/MemecoinRadar (PRIVATE, 51 dosya, `main` → `origin/main`).
- Yüklemeden önce kontrol: depoda `.env`, veritabanı, loglar, `config.yaml`, paketler yok.
- Bu kurulumda `updater.check()` gerçek depoyla çalışıyor (0 yeni değişiklik).
- **Bundan sonra güncelleme yayınlamak:** değişiklikler commit edilip `git push` yapılır; arkadaşların panelinde "🔔 Yeni sürüm var" çıkar.
- Kalan: arkadaşları depoya davet etmek (GitHub → depo → Settings → Collaborators), Windows'ta başlatıcı döngüsünü denemek.

---

## 2026-10-08 — Arkadaşlarla paylaşım: GitHub + Güncelle butonu (hazırlık)

**Durum:** Hazırlık tamam ve test edildi; GitHub'a yükleme kullanıcının son onayını bekliyor.
**Kullanıcı kararları:** 2–3 arkadaş farklı yerlerde kullanacak; GitHub hesabı var; depo **gizli** olacak; önce hazırlık, yükleme ayrıca onaylanacak.

**Yapılanlar**
- `config.yaml` git takibinden çıkarıldı (`.gitignore`): her kurulumun kendi ayarı; güncellemeler ezmez. Dosya yoksa program varsayılanlarla oluşturur.
- `radar/updater.py`: `check()` (git fetch, kaç yeni commit, başlıkları, elle değiştirilmiş dosyalar), `apply()` (`git pull --ff-only`; requirements.txt değiştiyse `pip install`). Elle değiştirilmiş kod dosyası varsa güncelleme yapılmaz.
- Yeniden başlatma: panel `restart_requested_at` yazar ve 75 koduyla kapanır; `start.command`/`start.bat` döngüsü paneli yeni sekme açmadan yeniden açar. Tarama servisi isteği bir sonraki bekleme anında görür ve `os.execv` ile kendini yeni kodla açar (Mac'te süreç numarası aynı kalır; başlatıcının kapatma takibi bozulmaz). Yarım tarama kesilmez.
- Panel: Sistem → **Güncellemeler** (kurulu sürüm, Denetle, yenilikler listesi, Güncelle); yeni sürüm varsa sol menüde "🔔 Yeni sürüm var" (10 dakikada bir denetim). Sürüm artık commit kodu + tarihi olarak gösteriliyor.
- README: "Arkadaşlar için kurulum (GitHub'dan)" (gh kurulumu, `gh auth login`, `gh repo clone`, herkesin kendi anahtarları) ve "Güncelleme".
- Testler: 99 (geçici bare repo + iki klon ile güncelleme akışı; internet yok). Test, porcelain çıktısında dosya adının ilk harfinin kesildiği bir hatayı yakaladı (düzeltildi).
- Elle test: kopya klasörde tarama servisi yeniden başlatma isteğini tur bitince gördü ve kendini yeniden açtı.

**Bulgular**
- Bu oturumda GitHub MCP bağlantısı yok (kullanıcı bağlı olduğunu düşünüyordu). `gh` kurulu değil; Homebrew var.
- Git geçmişinde anahtar/chat ID/bot adı yok; `.env` hiç commit edilmemiş. Commit yazar e-postası görünür (gizli depoda sadece davetliler görür).

**Kalan adımlar (onaydan sonra)**
- GitHub'da gizli depo oluşturma ve ilk yükleme (gh veya GitHub bağlantısı ile), `origin` + upstream ayarı.
- Arkadaşları depoya davet etme (kullanıcı yapacak).
- README'deki `DEPO_SAHIBI` yerine gerçek kullanıcı adı.
- Windows başlatıcısındaki döngü Windows'ta denenmedi.

---

## 2026-10-08 — Aşama 5: Takip ve haftalık özet

**Durum:** Kod tamam, sahte veriyle panelde denendi. Gerçek sonuçlar için veri birikmesi gerekiyor (ilk 24 saatlik sonuçlar ilk uyarıdan 24 saat sonra). Kullanıcı Aşama 4 bildirimlerini doğruladı.

**Yapılanlar**
- `radar/tracking.py`: üç grup — `alert` (uyarı verilen her token), `low` (eşik altı skorlulardan örnek), `veto` (elenenlerden örnek). Örnekleme adrese göre sabit (%30, `control_sample_pct`). Seçildiği andaki fiyat/MC/likidite kaydedilir; 1, 6, 24 saat sonra DexScreener'dan ölçülür. Bilgisayar uyuduysa ölçüm geç yapılır, gerçek zamanı saklanır.
- Sonuç: 24 saatte MC +%50 → yükseldi; −%70 veya likidite < $1.000 (ya da DexScreener'dan kaybolmuş) → çöktü; arası yatay. Eşikler ayarlardan.
- Haftalık özet: grup başına yükselme/çöküş oranı ve ortanca değişim; her grupta ≥5 sonuç varsa "uyarılar düşük skorlulara göre daha iyi/kötü/benzer"; en sık eleme sebepleri. Varsayılan Pazartesi 10:00 (Türkiye); bilgisayar kapalıysa açılınca gider.
- `tracking` tablosu; yeni ayarlar (Takip grubu): `control_sample_pct`, `outcome_up_pct`, `outcome_crash_pct`, `weekly_summary_enabled/day/hour`.
- Skor turu artık her skorlanan token için karşılaştırma örneklemesi yapıyor; Telegram ayarlı değilse de skorlama ve takip sürüyor.
- Panel: **Performans** sayfası (grup kartları, 24 saat sonuç çubukları, skor aralığı tablosu, takip edilen tokenlar 1/6/24 saat değişimiyle, haftalık özet önizlemesi + "Şimdi gönder").
- Terminal: `python main.py --weekly` önizleme.
- Testler: 93.

**Bilinen eksikler**
- Aşama 5'ten önce gönderilmiş uyarılar takipte yok (başlangıç değerleri bilinmiyor).
- Bir token önce "düşük skor" grubuna girip sonra uyarı alırsa iki grupta da durur (seçildiği andaki duruma göre dürüst ama karşılaştırmayı biraz bulandırabilir).
- MC değişimi kullanılıyor; MC yoksa fiyat değişimi.

---

## 2026-10-08 — Anahtarlar panelden, şifreli kasada

- Kullanıcı isteği: API anahtarları panelden girilsin, dosya olarak taşınmasın. (Kullanıcı Aşama 4 bildirimlerinin sorunsuz geldiğini doğruladı.)
- `radar/keys.py`: anahtarlar `keyring` ile işletim sistemi kasasında (Mac Anahtar Zinciri / Windows Kimlik Bilgisi Yöneticisi), servis adı `MemecoinRadar`. Kasada yoksa `.env`/ortam değişkeni yedek olarak okunur (kasası olmayan sunucular için).
- `notify` ve `helius` artık anahtarları `keys.get()` ile alıyor. Yeni: `notify.check_bot_token()`, `helius.check_key()` (kaydetmeden önce doğrulama; hata mesajlarında anahtar yok).
- Panel → Ayarlar → **Bağlantı anahtarları**: her anahtarın durumu (kasada / .env'de / yok; değer asla gösterilmez), şifre kutusu + doğrulayarak kaydet, sil, "Chat ID'mi bilmiyorum" (bot'a yazanları bulup tek tıkla kaydetme), ".env'deki anahtarları kasaya taşı" (taşınıp geri okunabildiği doğrulananlar .env'den silinir).
- Taşıma düğmesine Claude basmadı; kullanıcı kendisi basacak.
- `start.command`/`start.bat`'taki ".env yok" uyarısı kaldırıldı; README kurulum adımları panel üzerinden; `.env.example` artık "normalde gerekmez" diyor; `keyring==25.7.0` requirements'ta.
- Testler: 82 (bellekte sahte kasa; gerçek Anahtar Zinciri'ne dokunulmuyor).
- Not: Python sürümü değişirse (ör. yeni Python kurulumu) Mac, kasaya erişim için bir kez izin isteyebilir.

---

## 2026-10-08 — Aşama 4: Skor ve Telegram uyarısı

**Durum:** Kod tamam; gerçek bir token için test uyarısı Telegram'a gönderildi. Kullanıcının programı yeniden başlatıp ilk gerçek uyarıları görmesi bekleniyor.

**Yapılanlar**
- `radar/scoring.py`: 0–100 skor (whale akışı 50 + alıcı çeşitliliği 30 + likidite/MC 20 − risk cezası). Veto → skor yok. Sonuç ve döküm `scores` tablosunda (JSON).
- `radar/alerts.py`: skor turu, uyarı kararı (eşik 60, 6 saat bekleme, skor +15 artarsa beklemeden), Telegram mesajı (HTML, token adları kaçırılıyor; DexScreener ve X linkleri), `alerts` tablosu. Deneme modunda gönderilmez ama kaydedilir. Gönderim başarısızsa bir sonraki turda tekrar denenir.
- Günlük "çalışıyorum" özeti (`heartbeat_hours`, ilk açılışta hemen atmaz). Tarama art arda 3 kez hata verirse Telegram'a bir kez haber.
- `radar/fmt.py`: ortak tutar/süre biçimi (panel ve mesaj aynı).
- Yeni ayar: `risk_warn_penalty` (8). Aşama 4 ayarları panelde açıldı.
- Akış: tespit → risk (60 dk) → akış (15 dk) → (risk veya akış yenilendiyse) skor + uyarı → heartbeat.
- Terminal: `--token ADRES` artık skor ve mesaj önizlemesini de gösterir; `--send-alert` ile test uyarısı.
- Panel: **Uyarılar** sayfası (geçmiş, mesaj önizlemesi), token listesinde Skor çubuğu, token detayında skor kartı (bileşen çubukları), Genel Bakış'ta "Uyarı (24 saat)".
- Testler: 74.

**Bulgular**
- 19 tokenlık ilk dağılım: 4 token ≥60 (Mario64 84→92, Babem 81, OMARCHY 80, Gunner 64), net çıkış olanlar 0–12, veto almış olanlar skorsuz. Formül makul ayrıştırıyor.
- "USDT" görünen token aslında "ՍЅᎠТ" (Ermeni/Kiril harfli taklit). Kopya kontrolü harf benzerliği hilelerini yakalamıyor.
- Test uyarısı (Mario64, 92/100) Telegram'a gönderildi.

**Bilinen eksikler**
- Akışı okunamayan tokenlar (Meteora/Raydium, SOL dışı havuzlar) whale puanı alamadığı için pratikte uyarı alamaz (en fazla ~20 puan).
- Harf hileli taklit tokenlar (ՍЅᎠТ gibi) için kontrol yok.
- Skor sınırları tahmin; Aşama 5 verisiyle ayarlanmalı.
- Telegram komutları (`/token` vb.) yok (planda "Ek (sonra)").
- Yeniden başlatınca ilk turda eşiği geçen birkaç token için aynı anda uyarı gelebilir.

---

## 2026-10-08 — Panel: yeni tasarım

- Kullanıcı bir örnek tasarım gönderdi (koyu yeşil zemin, yuvarlak kartlar, limon yeşili vurgu, parlayan çizgi grafik, solda menü, üstte özet kartları). Streamlit'te kalınarak buna yaklaşıldı; birebir için paneli baştan yazmak gerekirdi (kullanıcıya söylendi).
- `.streamlit/config.toml`: koyu yeşil tema, limon vurgu (#c5f23a), yuvarlak köşeler, kenar çubuğu rengi.
- `panel_ui.py`: CSS ve HTML parçaları (özet kartları, liste kartları, rozetler, renkli sembol avatarları). Dış metinler (token adları) `esc()` ile kaçırılıyor.
- `radar/stats.py`: Genel Bakış verileri (özet, saatlik whale akışı, öne çıkanlar, son işlemler, risk uyarıları) + 5 test.
- Sayfalar: **Genel Bakış** (yeni ana sayfa: 4 özet kartı, 24 saatlik birikimli whale akışı grafiği, öne çıkanlar, son büyük işlemler, risk uyarıları), **Tokenlar** (token detayı: başlık kartı, özet kartları, X/DexScreener butonları, grafik, risk ve cüzdan kartları yan yana), **Ayarlar** (grup kartları, iki sütun), **Sistem** (eski Durum: tur zamanları, Helius kredisi, bağlantılar, loglar).
- `static/logo.svg`, menü ikonları (Material).
- Grafik: Altair'e veri ham sözlükle verilince çizgi çizilmiyordu; pandas DataFrame ile düzeldi. `altair` ve `pandas` requirements'a sabitlendi.
- Testler: 57.

---

## 2026-10-08 — Panel: X'te arama

- Kullanıcı isteği: seçilen coin için tek tuşla X araması (değerlendirmeler X'te yaygın).
- Token detayında iki buton: "Adresle ara" (kontrat adresi; kopya/aynı isimli coinlerle karışmaz) ve "$SEMBOL ara" (daha çok sonuç, yaygın sembollerde gürültülü). Ayrıca "DexScreener'da aç". Token listesine "𝕏 ara" sütunu.
- API yok, ücret yok: `x.com/search?q=…&f=live` (en yeniler) linki kullanıcının tarayıcısında açılır.
- Kullanıcı arayüzü beğenmiyor; örnek arayüzler isteyecek. Sonraki adım: örneklere göre panel tasarımı.

---

## 2026-10-08 — Uyku engeli ve temiz kapanış

- Aşama 3 + grafik commit edildi.
- Kullanıcı grafiği kendi tarayıcısında doğruladı: açılıyor. Olduğu gibi bırakıldı.
- `start.command`: `caffeinate -i -w $$` eklendi. Pencere açıkken Mac boşta uyumaz; betik biterse caffeinate de biter. Kapak kapanınca Mac yine uyur.
- Bulunan açık: Ctrl+C'de arka plandaki tarama servisi sinyali görmezden geliyor (betikteki arka plan işleri SIGINT'i yok sayar), sonra temizlenmeden öldürülüyordu. Düzeltme: betikte INT/HUP/TERM → temiz kapanış; `main.py` SIGTERM/SIGHUP'ı Ctrl+C gibi işler (log "Durduruldu", `stopped_at` yazılır).
- Test (kopya klasör, ayrı port): Ctrl+C ve pencere kapatma (SIGHUP) senaryolarında tarama, panel ve caffeinate birlikte kapandı; uyku engeli çalışırken aktifti; geride süreç kalmadı.
- Eksik: Windows'ta (`start.bat`) uyku engeli yok.

---

## 2026-10-08 — Panel: token grafiği

- Kullanıcı isteği: token seçilince DexScreener grafiği. Token detayına DexScreener'ın gömülebilir sayfası eklendi (`?embed=1&theme=dark`, yükseklik 650). Grafik tarayıcıda doğrudan DexScreener'dan yüklenir.
- Denenen ek parametreler (`info=0`, `trades=0`, `chartLeftToolbar=0` vb.) ile grafik "Loading pair..." ekranında takıldı; sade parametrelere dönüldü.
- Claude'un test tarayıcısında yükleme 30–40 sn sürdü, bazen hiç gelmedi; ilk açılışta "Info" sekmesi geliyor, "Chart" düğmesiyle grafiğe geçiliyor. Kullanıcının kendi tarayıcısında doğrulanması gerekiyor.
- Yedek: DexScreener linki grafiğin altında. Gerekirse alternatif: GeckoTerminal'in gömülebilir grafiği.

---

## 2026-10-08 — Aşama 3: Risk kontrolleri

**Durum:** Kod tamam, gerçek veriyle denendi. Kullanıcının panelde incelemesi bekleniyor.
İlk git commit'i bu aşamadan önce yapıldı (Aşama 0–2).

**Yapılanlar**
- `radar/sources/rugcheck.py`: RugCheck raporu (ücretsiz, anahtarsız, dakikada 15 istek → istekler arası 4,5 sn).
- `radar/risk.py`: 10 kontrol, her biri ok / info / warn / veto / unknown + Türkçe açıklama. Sonuçlar `risk_checks` tablosunda.
  - RugCheck'ten: mint yetkisi, freeze yetkisi, Token-2022 (transfer ücreti, kalıcı yetkili), rugged işareti, ilk 10 cüzdan payı (havuz/kilit/yakım adresleri hariç), LP kilidi, bağlantılı cüzdan ağları.
  - Kendi verimizden: aynı saniyede ≥3 cüzdanın aynı yönde büyük işlemi (toplu işlem), aynı isimde daha eski token (kopya).
  - Helius'tan: dev satışı (`dev_state` tablosu, artımlı; dev'in elinde token kalmadıysa yeniden sorgulanmaz).
- Sıra: tespit → risk (60 dk'da bir) → akış (15 dk'da bir). Veto alan tokenın akışı izlenmez (kredi tasarrufu).
- Yeni ayar: `risk_interval_minutes` (60).
- Panel: token listesinde Risk sütunu; token detayında kontrol listesi. Markdown'da `$` formül sanılıyordu, kaçırıldı.
- Terminal: `python main.py --token ADRES` artık risk kontrollerini de gösterir.
- Testler: 52 test, hepsi geçiyor (gerçek RugCheck raporu fixture'ı dahil).

**Kararlar ve nedenleri**
- "Aynı kaynaktan fonlanan cüzdanlar" için kendi analizimiz ve borsa cüzdan listesi yerine RugCheck'in bağlantılı ağ (insider network) analizi kullanıldı: ücretsiz, hazır ve borsa adreslerini ezberden uydurma riski yok. Helius Wallet API (fonlama kaynağı) cüzdan başına 100 kredi.
- Dev satışı = dev'in o tokendan elinden çıkardığı / aldığı. Başka cüzdana aktarım da sayılır (çoğu zaman satışa hazırlık).
- Kalıcı yetkili (permanent delegate) freeze ile aynı ayara bağlandı (veto): ikisi de tokenlarınızı elinizden alabilir.

**Bulgular (ilk tur, 20 token)**
- 9 token veto aldı; 8'inde sebep **dev satışı %93–100**. Pump.fun'da dev'in hepsini satması çok yaygın; %50 kuralı tokenların yarısını eliyordu.
  → **Kullanıcı kararı: dev satışı sadece uyarı.** Yeni ayar `veto_if_dev_sold` (varsayılan kapalı); açılırsa `dev_sold_veto_pct` eşiği kullanılır. Aşama 5 verisiyle bu tokenların sonucu ölçülüp tekrar değerlendirilecek. Yeni kuralla: 20 tokendan 1'i veto (WLD, mint yetkisi).
- USDC ile negatif test: mint ve freeze yetkisi doğru şekilde ⛔.
- XRPN: dev 793M token almış (arzın ~%79'u), hepsini elden çıkarmış; ayrıca 6 cüzdanlık toplu satış yakalandı.
- 5 tokenda bağlantılı ağlar arzın ≥%5'ini tutuyor; 4 tokenda LP kilidi düşük (Meteora/Raydium havuzları).
- Maliyet: risk turu (20 token) ≈ 100–200 Helius kredisi; RugCheck turu ~90 sn.

**Bilinen eksikler**
- Toplu işlem tespiti sadece izlenen büyük işlemlere bakar; küçük işlemlerle yapılan bundle'lar görünmez.
- Kopya tespiti sadece programın gördüğü tokenlar arasında.
- RugCheck'e bağımlılık: RugCheck cevap vermezse çoğu kontrol "bilinmiyor" olur (program çökmez).
- Çalışan tarama servisi ve panel eski kodla açık; yeniden başlatılmalı.

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
- ~~Mac uykuya geçince tarama duruyor.~~ Çözüldü: `start.command`'da `caffeinate` (kapak kapanınca yine uyur; kalıcı çözüm Aşama 7).
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
