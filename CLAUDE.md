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
- Gizli anahtarlar (bot token, chat ID, Helius) işletim sistemi kasasında (`radar/keys.py`); yedek olarak `.env`. Değerlerini asla ekrana basma, loglama veya dosyaya yazma.
- Testler: `.venv/bin/python -m unittest`

Sürüm ve yayın (kod herkese açık GitHub deposunda: dinjon4/MemecoinRadar — kullanıcı kararı 2026-10-09;
arkadaşlar panelden "Güncelle" ile alır):
- Sürüm `radar/__init__.py` içindeki `VERSION` (anlamsal sürümleme). Yükseltme kararını Claude verir:
  hata düzeltmesi/küçük iyileştirme → son rakam (1.0.1), yeni özellik/aşama → orta (1.1.0),
  kurulumu bozan/veri sıfırlayan değişiklik → ilk (2.0.0).
- Her yayında: `VERSION`'ı artır, `CHANGELOG.md`'nin en üstüne `## vX.Y.Z — YYYY-MM-DD` başlığıyla sade Türkçe notlar ekle,
  testler geçsin, commit, `git tag vX.Y.Z`, `git push --follow-tags`. Sürüm artırmadan push etme
  (sadece belge/yorum değişikliği bile olsa son rakamı artır).
- `kurulum/` içindeki betikler değişirse herkese açık Gist'i de güncelle (tek satırlık kurulum komutu oradan çalışır):
  `gh gist edit b48b601a6dd4fc5b3bb0a35b88cf3dfc -f kurulum.command kurulum/kurulum.command` (kurulum.ps1 için de aynısı).
  Gist'e program kodu veya gizli bilgi konmaz.
- Yayın izni (kullanıcı kararı, 2026-10-08): testler geçince sürüm yükseltilip **sormadan** gönderilir;
  gönderdikten sonra kullanıcıya hangi sürümün ne içerdiği kısaca bildirilir.
  Depo herkese açık: commit'lere asla gizli/kişisel bilgi (anahtar, chat ID, bot adı, e-posta) girmez;
  commit e-postası GitHub'ın gizli adresi (repo içi `user.email` ayarlı). Belgelere commit kodu yazılmaz, sürüm adı yazılır.
