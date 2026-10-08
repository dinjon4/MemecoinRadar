"""config.yaml okuma, doğrulama ve kaydetme.

Tüm ayarların tanımı (varsayılan değer, sınırlar, açıklama) SETTINGS listesinde durur.
config.yaml bu listeden üretilir; panel de formlarını bu listeden kurar.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

import yaml

from radar import CONFIG_PATH

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Setting:
    key: str          # iç içe ayarlar için nokta ile: "score_weights.whale_net_flow"
    type: type        # int, float veya bool
    default: Any
    label: str
    help: str
    group: str
    stage: int        # bu ayarın kullanılmaya başlandığı aşama
    min: float | None = None
    max: float | None = None


SETTINGS: list[Setting] = [
    # Tarama
    Setting("scan_interval_minutes", int, 3, "Tarama sıklığı (dakika)",
            "Kaç dakikada bir tarama yapılacağı.", "Tarama", 0, 1, 1440),
    Setting("token_max_age_hours", int, 24, "En fazla token yaşı (saat)",
            "Sadece bu kadar yeni tokenlar izlenir.", "Tarama", 1, 1, 168),
    Setting("min_liquidity_usd", int, 10000, "En az likidite ($)",
            "Likiditesi bunun altında olan tokenlar elenir.", "Tarama", 1, 0, 10_000_000),
    Setting("include_bonding_curve", bool, False, "Bonding curve tokenları dahil",
            "Pump.fun'da henüz havuza geçmemiş tokenlar da izlensin mi.", "Tarama", 1),
    # Cüzdan akışı
    Setting("whale_min_usd", int, 1500, "Whale eşiği ($)",
            "Bu tutarın üstündeki alım/satımlar 'whale' sayılır.", "Cüzdan akışı", 2, 100, 10_000_000),
    Setting("flow_interval_minutes", int, 15, "Cüzdan akışı sıklığı (dakika)",
            "Cüzdan akışı kaç dakikada bir güncellenir. Sıklaştırmak Helius kredisini hızlı tüketir.",
            "Cüzdan akışı", 2, 5, 1440),
    Setting("flow_max_tokens", int, 20, "İzlenecek en fazla token (akış ve risk)",
            "Her turda hacmi en yüksek bu kadar tokenın akışı ve risk kontrolü güncellenir.", "Cüzdan akışı", 2, 1, 100),
    Setting("helius_daily_credit_budget", int, 30000, "Helius günlük kredi bütçesi",
            "Bu kadar kredi harcanınca akış ertesi güne kadar durur. Ücretsiz plan ayda 1M kredi (~33K/gün).",
            "Cüzdan akışı", 2, 100, 10_000_000),
    # Risk
    Setting("risk_interval_minutes", int, 60, "Risk kontrolü sıklığı (dakika)",
            "Risk kontrolleri kaç dakikada bir yenilenir. Dev satışı kontrolü Helius kredisi harcar.",
            "Risk", 3, 10, 1440),
    Setting("top10_holder_warn_pct", int, 40, "İlk 10 cüzdan uyarı eşiği (%)",
            "İlk 10 cüzdan (havuz/burn hariç) arzın bu yüzdesinden fazlasını tutuyorsa uyar.", "Risk", 3, 1, 100),
    Setting("veto_if_dev_sold", bool, False, "Dev satışında ele",
            "Kapalıyken dev satışı sadece uyarıdır. Açıkken aşağıdaki eşiği aşan tokenlar elenir.", "Risk", 3),
    Setting("dev_sold_veto_pct", int, 50, "Dev satış eleme eşiği (%)",
            "'Dev satışında ele' açıksa: dev elindekinin bu yüzdesinden fazlasını sattıysa token elenir.",
            "Risk", 3, 1, 100),
    Setting("veto_if_mint_authority", bool, True, "Mint authority açıksa ele",
            "Dev yeni token basabiliyorsa token elenir.", "Risk", 3),
    Setting("veto_if_freeze_authority", bool, True, "Freeze authority açıksa ele",
            "Dev tokenları dondurabiliyorsa token elenir.", "Risk", 3),
    # Skor ve uyarı
    Setting("min_score_to_alert", int, 60, "En düşük uyarı skoru",
            "Bu skorun altındaki tokenlar Telegram'a gönderilmez.", "Skor ve uyarı", 4, 0, 100),
    Setting("score_weights.whale_net_flow", int, 50, "Ağırlık: whale net akışı",
            "Skor ağırlığı. Üç ağırlığın toplamı 100 olmalı.", "Skor ve uyarı", 4, 0, 100),
    Setting("score_weights.buyer_diversity", int, 30, "Ağırlık: alıcı çeşitliliği",
            "Skor ağırlığı. Üç ağırlığın toplamı 100 olmalı.", "Skor ve uyarı", 4, 0, 100),
    Setting("score_weights.liquidity_to_mc", int, 20, "Ağırlık: likidite/MC oranı",
            "Skor ağırlığı. Üç ağırlığın toplamı 100 olmalı.", "Skor ve uyarı", 4, 0, 100),
    Setting("risk_warn_penalty", int, 8, "Risk uyarısı başına ceza (puan)",
            "Her ⚠️ risk uyarısı skordan bu kadar puan düşürür.", "Skor ve uyarı", 4, 0, 50),
    Setting("alert_cooldown_hours", int, 6, "Tekrar uyarı bekleme süresi (saat)",
            "Aynı token için bu süre dolmadan tekrar uyarı gönderilmez.", "Skor ve uyarı", 4, 0, 168),
    Setting("realert_score_jump", int, 15, "Erken tekrar uyarı için skor artışı",
            "Skor bu kadar artarsa bekleme süresi beklenmeden tekrar uyarılır.", "Skor ve uyarı", 4, 1, 100),
    # Takip
    Setting("control_sample_pct", int, 30, "Karşılaştırma grubu oranı (%)",
            "Uyarı almayan tokenların bu kadarı karşılaştırma için izlenir.", "Takip", 5, 0, 100),
    Setting("outcome_up_pct", int, 50, "'Yükseldi' eşiği (%)",
            "24 saat sonra piyasa değeri bu kadar arttıysa 'yükseldi' sayılır.", "Takip", 5, 1, 10000),
    Setting("outcome_crash_pct", int, 70, "'Çöktü' eşiği (%)",
            "24 saat sonra piyasa değeri bu kadar düştüyse (veya likidite boşaltıldıysa) 'çöktü' sayılır.",
            "Takip", 5, 1, 100),
    Setting("weekly_summary_enabled", bool, True, "Haftalık özet gönder",
            "Her hafta Telegram'a performans özeti gönderilir.", "Takip", 5),
    Setting("weekly_summary_day", int, 1, "Haftalık özet günü (1=Pzt … 7=Paz)",
            "Özetin gönderileceği gün.", "Takip", 5, 1, 7),
    Setting("weekly_summary_hour", int, 10, "Haftalık özet saati",
            "Türkiye saatiyle. Bilgisayar o saatte kapalıysa açılınca gönderilir.", "Takip", 5, 0, 23),
    # Haber
    Setting("news_enabled", bool, True, "Haber/trend eşleştirme",
            "Haber ve trend başlıkları token adlarıyla eşleştirilir; eşleşme 'Hikâye' olarak gösterilir.", "Haber", 6),
    Setting("news_interval_minutes", int, 30, "Haber okuma sıklığı (dakika)",
            "Haber kaynakları kaç dakikada bir okunur.", "Haber", 6, 10, 1440),
    Setting("news_lookback_hours", int, 48, "Hikâye zaman aralığı (saat)",
            "Tokenın çıkışından en fazla bu kadar önceki haberlere bakılır.", "Haber", 6, 1, 96),
    # Çalışma
    Setting("dry_run", bool, False, "Deneme modu (dry run)",
            "Açıksa Telegram'a mesaj gönderilmez, sadece terminale ve loga yazılır.", "Çalışma", 0),
    Setting("heartbeat_hours", int, 24, "'Çalışıyorum' mesajı sıklığı (saat)",
            "Bu aralıkla Telegram'a özet mesajı gönderilir. 0 = kapalı.", "Çalışma", 4, 0, 168),
]

SETTINGS_BY_KEY = {s.key: s for s in SETTINGS}
SCORE_WEIGHT_KEYS = [s.key for s in SETTINGS if s.key.startswith("score_weights.")]


class ConfigError(Exception):
    """Ayar dosyası okunamadı veya geçersiz değer içeriyor."""


def defaults() -> dict:
    return {s.key: s.default for s in SETTINGS}


def _flatten(data: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in data.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, f"{key}."))
        else:
            flat[key] = v
    return flat


def _convert(setting: Setting, value: Any) -> Any:
    """Değeri doğru tipe çevirir; çevrilemezse ValueError."""
    if setting.type is bool:
        if isinstance(value, bool):
            return value
        raise ValueError("true veya false olmalı")
    if isinstance(value, bool):  # True/False sayı yerine kabul edilmesin
        raise ValueError("sayı olmalı")
    try:
        converted = setting.type(value)
    except (TypeError, ValueError):
        raise ValueError("sayı olmalı")
    if setting.type is int and float(value) != converted:
        raise ValueError("tam sayı olmalı")
    return converted


def validate(values: dict) -> tuple[dict, list[str]]:
    """Değerleri doğrular. (temiz_değerler, hata_listesi) döner. Hata yoksa liste boştur."""
    clean, errors = {}, []
    for s in SETTINGS:
        if s.key not in values:
            clean[s.key] = s.default
            continue
        try:
            v = _convert(s, values[s.key])
        except ValueError as e:
            errors.append(f"{s.key} ({s.label}): {e}. Verilen: {values[s.key]!r}")
            continue
        if s.min is not None and v < s.min:
            errors.append(f"{s.key} ({s.label}): en az {s.min:g} olmalı. Verilen: {v}")
        elif s.max is not None and v > s.max:
            errors.append(f"{s.key} ({s.label}): en fazla {s.max:g} olmalı. Verilen: {v}")
        clean[s.key] = v

    if not any(k not in clean for k in SCORE_WEIGHT_KEYS):
        total = sum(clean[k] for k in SCORE_WEIGHT_KEYS)
        if total != 100:
            errors.append(f"Skor ağırlıklarının toplamı 100 olmalı. Şu an: {total}")
    return clean, errors


def load(path=CONFIG_PATH) -> dict:
    """config.yaml'ı okur ve doğrular. Dosya yoksa varsayılanlarla oluşturur.

    Dönen sözlükte anahtarlar düzdür: cfg["score_weights.whale_net_flow"].
    Hatalı değer varsa ConfigError fırlatır.
    """
    if not path.exists():
        log.warning("config.yaml bulunamadı, varsayılan ayarlarla oluşturuluyor.")
        save(defaults(), path)
        return defaults()

    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml okunamadı (yazım hatası olabilir): {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml beklenen biçimde değil.")

    flat = _flatten(raw)
    for key in flat.keys() - SETTINGS_BY_KEY.keys():
        log.warning("config.yaml içinde bilinmeyen ayar yok sayıldı: %s", key)
    for key in SETTINGS_BY_KEY.keys() - flat.keys():
        log.warning("config.yaml içinde '%s' yok, varsayılan kullanılıyor: %r",
                    key, SETTINGS_BY_KEY[key].default)

    clean, errors = validate(flat)
    if errors:
        raise ConfigError("config.yaml hatalı:\n- " + "\n- ".join(errors))
    return clean


def _yaml_value(v: Any) -> str:
    return "true" if v is True else "false" if v is False else str(v)


def save(values: dict, path=CONFIG_PATH) -> None:
    """Değerleri doğrulayıp config.yaml'a yazar. Açıklamalar her seferinde yeniden eklenir."""
    clean, errors = validate(values)
    if errors:
        raise ConfigError("Ayarlar kaydedilmedi:\n- " + "\n- ".join(errors))

    lines = [
        "# Memecoin Radar ayarları",
        "# Bu dosya panelden de düzenlenebilir. Elle düzenlerseniz yapıyı bozmayın.",
    ]
    group = None
    open_parent = None
    for s in SETTINGS:
        if s.group != group:
            group = s.group
            open_parent = None
            lines += ["", f"# --- {group} ---"]
        parent, _, name = s.key.rpartition(".")
        indent = ""
        if parent:
            if parent != open_parent:
                lines.append(f"{parent}:")
                open_parent = parent
            indent = "  "
        lines.append(f"{indent}# {s.label}: {s.help}")
        lines.append(f"{indent}{name}: {_yaml_value(clean[s.key])}")
    text = "\n".join(lines).strip() + "\n"

    # Önce geçici dosyaya yaz, sonra değiştir: yazma yarıda kalırsa eski dosya bozulmaz.
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)
