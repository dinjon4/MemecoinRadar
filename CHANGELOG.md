# Sürüm notları

Panel → Sistem → Güncellemeler bölümü yeni sürümlerin notlarını bu dosyadan okur.
Biçim: her sürüm `## vX.Y.Z — YYYY-MM-DD` başlığı ve altında madde işaretli kısa, sade notlar.

Sürüm numarası kuralı:
- **Son rakam** (v1.0.1): hata düzeltmesi, küçük iyileştirme
- **Ortadaki rakam** (v1.1.0): yeni özellik, yeni aşama
- **İlk rakam** (v2.0.0): kurulumu etkileyen büyük değişiklik (ör. veriler sıfırlanır, yeniden kurulum gerekir)

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
