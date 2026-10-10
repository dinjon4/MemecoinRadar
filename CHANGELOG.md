# Sürüm notları

Panel → Sistem → Güncellemeler bölümü yeni sürümlerin notlarını bu dosyadan okur.
Biçim: her sürüm `## vX.Y.Z — YYYY-MM-DD` başlığı ve altında madde işaretli kısa, sade notlar.

Sürüm numarası kuralı:
- **Son rakam** (v1.0.1): hata düzeltmesi, küçük iyileştirme
- **Ortadaki rakam** (v1.1.0): yeni özellik, yeni aşama
- **İlk rakam** (v2.0.0): kurulumu etkileyen büyük değişiklik (ör. veriler sıfırlanır, yeniden kurulum gerekir)

## v2.1.0 — 2026-10-10
- Yeni: **Erken Hacim** (Aşama 8, 1. adım). Ayrı bir servis yeni açılan havuzların (pump.fun bonding curve dahil)
  hacim, alım/satım ve farklı alıcı sayısını dakika dakika kaydeder. Şimdilik **sadece veri toplar, uyarı göndermez**.
- Panelde yeni **Erken Hacim** sayfası: izlenen havuzlar, son 5 dk hacim, ivme, alıcı sayısı. "Veri toplamayı aç" düğmesi.
- Ayarlar → Erken Hacim: açma/kapama, ölçüm sıklığı, havuz yaşı, en fazla havuz, saklama süresi. Varsayılan kapalı.
- Mevcut tarama, skor ve uyarılar değişmedi. Tek fark: GeckoTerminal ve DexScreener istek hakkı iki servis arasında
  paylaşılıyor; tarama birkaç saniye yavaşlayabilir.
- 7/24 servis kuruluysa: yeni servisin de kurulması için `servis_kur.command`'ı bir kez daha çalıştırın.
- Yeni ayarlar `config.yaml`'a kendiliğinden eklenir.

## v2.0.1 — 2026-10-09
- Düzeltme: Yeni kurulan bir Mac'te panel açılmıyordu; Streamlit ilk açılışta Terminal'de e-posta soruyor ve cevap bekliyordu.
  Panel artık bu soruyu sormadan açılıyor, tarayıcıyı program kendisi açıyor.

## v2.0.0 — 2026-10-09
- Program artık **herkese açık** GitHub deposunda: kurulum için GitHub hesabı, davet veya giriş **gerekmez**.
- Kurulum sadeleşti: tek satır komut veya `kurulum.command` sadece Python ve git'i (gerekirse) kurar, programı indirir.
- Önemli: Daha önce (v1.3.1 ve öncesi) indirilmiş kurulumlar güncellenemez; klasörü silip yeniden kurun.
  Ayarlarınızı (`config.yaml`) ve verilerinizi (`data/`) saklamak isterseniz önce başka yere kopyalayın.

## v1.3.1 — 2026-10-08
- Tek satır komutla kurulum: Mac'te Terminal'e, Windows'ta PowerShell'e yapıştırılacak komutlar README'de.

## v1.3.0 — 2026-10-08
- Yeni: **tek adımda kurulum**. `kurulum/kurulum.command` (Mac) çift tıklanınca Python, git ve GitHub aracını
  gerekirse kurar, GitHub girişini ister, programı indirir, paketleri kurar, masaüstüne kısayol koyar ve açar.
  Kurulu bir bilgisayarda çalıştırılırsa sadece günceller.
- Windows için `kurulum/kurulum.bat` + `kurulum.ps1` (henüz Windows'ta denenmedi).

## v1.2.0 — 2026-10-08
- Yeni: **7/24 çalıştırma** (Aşama 7, evdeki Mac). `servis_kur.command` programı arka plan servisi olarak kurar:
  Mac açılınca kendiliğinden başlar, çökerse yeniden başlar, Mac'i uyutmaz. Kaldırmak için `servis_kaldir.command`.
- Servis kuruluyken `start.command` ikinci kopya açmaz, sadece paneli gösterir.
- README: evdeki Mac'i hazırlama, Telegram grubuna uyarı, paneli Tailscale ile arkadaşlarla paylaşma.

## v1.1.0 — 2026-10-08
- Yeni: **Hikâye** (Aşama 6). Haber ve trend başlıkları token adlarıyla eşleştirilir: Google Trends, Google News, Reddit, CoinDesk, Cointelegraph, Decrypt, The Block.
- Telegram uyarılarına "📰 Hikâye" satırı eklendi (haber linki, kaynağı, ne kadar önce).
- Panel: token detayında Hikâye kartı, token listesinde Hikâye sütunu.
- Yaygın kelimeler ("have", "test" gibi) tek başına eşleşme sayılmaz; yanlış eşleşmeler azaltıldı.
- Ayarlar → Haber: açma/kapama, okuma sıklığı, zaman aralığı.
- Arama sonucu boşsa artık doğru mesaj gösteriliyor.

## v1.0.0 — 2026-10-08
- İlk paylaşılan sürüm (Aşama 0–5).
- Yeni Solana tokenlarını bulur, likidite/yaş filtresi uygular.
- Büyük cüzdanların (whale) alım-satımlarını izler.
- Risk kontrolleri: mint/freeze yetkisi, dev satışı, holder yoğunluğu, LP kilidi, bağlantılı cüzdanlar, toplu işlem, kopya token.
- 0–100 skor ve Telegram uyarısı; günlük "çalışıyorum" özeti.
- Uyarılan tokenların 1/6/24 saat sonrası takibi, haftalık performans özeti.
- Panel: Genel Bakış, Tokenlar (DexScreener grafiği, X'te arama), Uyarılar, Performans, Ayarlar, Sistem.
- Anahtarlar panelden girilir, işletim sisteminin şifreli kasasında saklanır.
- Panelden tek tuşla güncelleme.
