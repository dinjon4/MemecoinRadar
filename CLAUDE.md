# Memecoin Radar — Claude Code için

İşe başlamadan önce sırayla oku:
1. `memecoin-radar-plan.md` — projenin tek kaynağı (amaç, kurallar, aşamalar).
2. `GELISTIRME_GUNLUGU.md` — şimdiye kadar ne yapıldı, hangi kararlar alındı, ne eksik.

Her çalışma oturumunun sonunda `GELISTIRME_GUNLUGU.md` dosyasının en üstüne yeni bir kayıt ekle
(yapılanlar, kararlar ve nedenleri, bulgular, bilinen eksikler).

Kurallar (ayrıntısı planda):
- Kullanıcı yazılımcı değil: Türkçe, sade, adım adım anlat.
- Aşama aşama ilerle; kullanıcı test etmeden sonraki aşamaya geçme.
- Sadece izleme. Alım-satım yok, private key / seed phrase asla yok.
- `.env` içeriğini (API anahtarları, bot token) asla ekrana basma veya loglama.
- Testler: `.venv/bin/python -m unittest`
