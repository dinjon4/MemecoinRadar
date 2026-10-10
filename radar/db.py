"""SQLite veritabanı. Tüm zamanlar UTC olarak ISO biçiminde saklanır."""

import sqlite3
from datetime import datetime, timezone

from radar import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS status (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    address         TEXT PRIMARY KEY,   -- token (mint) adresi
    name            TEXT,
    symbol          TEXT,
    created_at      TEXT,               -- tokenın ilk havuzunun açılışı (UTC)
    first_seen_at   TEXT NOT NULL,      -- programın tokenı ilk gördüğü an
    updated_at      TEXT NOT NULL,
    source          TEXT,               -- hangi listede bulundu
    pair_address    TEXT,
    dex             TEXT,
    url             TEXT,
    price_usd       REAL,
    market_cap_usd  REAL,
    liquidity_usd   REAL,
    volume_h24_usd  REAL,
    buys_h24        INTEGER,
    sells_h24       INTEGER,
    passed          INTEGER NOT NULL,   -- 1 = filtreleri geçti, 0 = elendi
    filter_reason   TEXT                -- elendiyse neden
);
CREATE INDEX IF NOT EXISTS idx_tokens_created ON tokens(created_at);

-- Aşama 2: havuzdaki büyük alım/satımlar
CREATE TABLE IF NOT EXISTS trades (
    signature     TEXT PRIMARY KEY,
    token         TEXT NOT NULL,      -- token (mint) adresi
    wallet        TEXT NOT NULL,
    side          TEXT NOT NULL,      -- 'buy' veya 'sell'
    token_amount  REAL NOT NULL,
    quote_amount  REAL NOT NULL,      -- havuza giren/çıkan SOL (veya USDC)
    usd           REAL NOT NULL,
    block_time    TEXT NOT NULL       -- UTC
);
CREATE INDEX IF NOT EXISTS idx_trades_token ON trades(token, wallet);

-- Her token için en son okunan işlem zamanı (sonraki turda sadece yenileri çekilir)
CREATE TABLE IF NOT EXISTS flow_state (
    token            TEXT PRIMARY KEY,
    last_block_time  INTEGER,         -- Unix saniye
    updated_at       TEXT NOT NULL
);

-- Cüzdanın elinde kalan token miktarı
CREATE TABLE IF NOT EXISTS wallet_balances (
    token       TEXT NOT NULL,
    wallet      TEXT NOT NULL,
    amount      REAL NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (token, wallet)
);

-- Aşama 3: risk kontrollerinin son sonucu (token ve kontrol başına bir satır)
CREATE TABLE IF NOT EXISTS risk_checks (
    token       TEXT NOT NULL,
    check_key   TEXT NOT NULL,
    level       TEXT NOT NULL,        -- ok / info / warn / veto / unknown
    title       TEXT NOT NULL,
    detail      TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (token, check_key)
);

-- Tokenı oluşturan cüzdanın (dev) o tokendaki hareketleri
CREATE TABLE IF NOT EXISTS dev_state (
    token            TEXT PRIMARY KEY,
    creator          TEXT,
    received         REAL NOT NULL DEFAULT 0,   -- dev'e giren token
    sent             REAL NOT NULL DEFAULT 0,   -- dev'den çıkan token (satış veya aktarım)
    last_block_time  INTEGER,
    updated_at       TEXT NOT NULL
);

-- Aşama 4: tokenın son skoru ve dökümü (details = JSON)
CREATE TABLE IF NOT EXISTS scores (
    token       TEXT PRIMARY KEY,
    score       INTEGER NOT NULL,
    details     TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Gönderilen (veya deneme modunda gönderilmiş sayılan) uyarılar
CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    token     TEXT NOT NULL,
    score     INTEGER NOT NULL,
    sent_at   TEXT NOT NULL,
    dry_run   INTEGER NOT NULL,      -- 1 = deneme modunda, Telegram'a gitmedi
    message   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_token ON alerts(token, sent_at);

-- Aşama 5: takip edilen tokenlar (uyarı grubu ve karşılaştırma grupları)
CREATE TABLE IF NOT EXISTS tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT NOT NULL,
    cohort      TEXT NOT NULL,        -- alert / low / veto
    score       INTEGER,              -- seçildiği andaki skor (veto ise boş)
    started_at  TEXT NOT NULL,
    price_0 REAL, mc_0 REAL, liq_0 REAL,
    price_1h REAL,  mc_1h REAL,  liq_1h REAL,  checked_1h TEXT,
    price_6h REAL,  mc_6h REAL,  liq_6h REAL,  checked_6h TEXT,
    price_24h REAL, mc_24h REAL, liq_24h REAL, checked_24h TEXT,
    done        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (token, cohort)
);

-- Aşama 6: haber/trend başlıkları (token adlarıyla eşleştirmek için)
CREATE TABLE IF NOT EXISTS news (
    id            TEXT PRIMARY KEY,   -- kaynak+başlık+adres özeti
    source        TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT,
    published_at  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    text          TEXT NOT NULL       -- eşleştirmede kullanılan metin
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at);

-- Aşama 8 (Erken Hacim, ayrı süreç: early.py): izlenen yeni havuzlar
CREATE TABLE IF NOT EXISTS ev_pools (
    pool           TEXT PRIMARY KEY,    -- havuz (pair) adresi
    chain          TEXT NOT NULL,       -- 'solana' (BNB Chain sonra)
    token          TEXT NOT NULL,       -- memecoin adresi
    name           TEXT,
    symbol         TEXT,
    dex            TEXT,
    created_at     TEXT NOT NULL,       -- havuzun açılışı (UTC)
    first_seen_at  TEXT NOT NULL,
    last_listed_at TEXT NOT NULL,       -- GeckoTerminal listelerinde en son görüldüğü an
    last_active_at TEXT,                -- son 5 dk'da işlem görüldüğü en son ölçüm
    source         TEXT,                -- ilk görüldüğü liste
    url            TEXT
);
CREATE INDEX IF NOT EXISTS idx_ev_pools_created ON ev_pools(created_at);

-- Havuzların dakikalık anlık görüntüleri. source: 'gt' (GeckoTerminal; benzersiz alıcı ve 15 dk dahil)
-- veya 'ds' (DexScreener; benzersiz alıcı ve 15 dk yok). Hacimler $; mX/hX = son 5 dk, 15 dk, 1 saat.
CREATE TABLE IF NOT EXISTS ev_snapshots (
    pool            TEXT NOT NULL,
    taken_at        TEXT NOT NULL,
    source          TEXT NOT NULL,
    price_usd       REAL,
    market_cap_usd  REAL,
    liquidity_usd   REAL,
    m5_volume REAL,  m5_buys INTEGER,  m5_sells INTEGER,  m5_buyers INTEGER,  m5_sellers INTEGER,
    m15_volume REAL, m15_buys INTEGER, m15_sells INTEGER, m15_buyers INTEGER, m15_sellers INTEGER,
    h1_volume REAL,  h1_buys INTEGER,  h1_sells INTEGER,  h1_buyers INTEGER,  h1_sellers INTEGER,
    PRIMARY KEY (pool, taken_at, source)
);
CREATE INDEX IF NOT EXISTS idx_ev_snapshots_taken ON ev_snapshots(taken_at);

-- Ücretli/limitli API'lerin tahmini kredi kullanımı (gün başına)
CREATE TABLE IF NOT EXISTS api_usage (
    day      TEXT NOT NULL,           -- YYYY-MM-DD (UTC)
    service  TEXT NOT NULL,
    credits  INTEGER NOT NULL,
    calls    INTEGER NOT NULL,
    PRIMARY KEY (day, service)
);
"""

# Sonradan eklenen sütunlar: eski veritabanlarına otomatik eklenir.
MIGRATIONS = {
    "tokens": {
        "quote_mint": "TEXT",
        "quote_price_usd": "REAL",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL: tarama servisi yazarken panel aynı anda okuyabilsin.
    conn.execute("PRAGMA journal_mode=WAL")
    init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Tabloları oluşturur ve eksik sütunları ekler."""
    conn.executescript(SCHEMA)
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, sql_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
    conn.commit()


def add_usage(conn: sqlite3.Connection, service: str, credits: int) -> None:
    day = datetime.now(timezone.utc).date().isoformat()
    conn.execute(
        "INSERT INTO api_usage (day, service, credits, calls) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(day, service) DO UPDATE SET credits = credits + excluded.credits, calls = calls + 1",
        (day, service, credits),
    )
    conn.commit()


def usage_today(conn: sqlite3.Connection, service: str) -> int:
    day = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute("SELECT credits FROM api_usage WHERE day = ? AND service = ?", (day, service)).fetchone()
    return row[0] if row else 0


def set_status(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO status (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, None if value is None else str(value), utc_now()),
    )
    conn.commit()


def get_status(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM status")}
