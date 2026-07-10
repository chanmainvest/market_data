-- ============================================================================
-- market_data initial schema
-- TimescaleDB on Postgres 16
-- Loaded at first boot via /docker-entrypoint-initdb.d/00-init.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
-- fuzzystrmatch: levenshtein() distance for "did you mean?" ticker suggestions.
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

-- ---------------------------------------------------------------------------
-- Reference tables (regular, no hypertable)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_ticker (
    ticker              TEXT PRIMARY KEY,
    type                TEXT,                       -- 'stock' | 'etf' | 'index'
    description         TEXT,
    is_etfcom           BOOLEAN DEFAULT FALSE,
    is_etfdb            BOOLEAN DEFAULT FALSE,
    w_sp500             DOUBLE PRECISION,
    w_nasdaq100         DOUBLE PRECISION,
    w_dowjones          DOUBLE PRECISION,
    earnings_report_time TEXT,                       -- 'before' | 'after' | NULL
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_etfdb_info (
    ticker      TEXT PRIMARY KEY,
    description TEXT,
    info        JSONB,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_etfcom_info (
    ticker      TEXT PRIMARY KEY,
    description TEXT,
    info        JSONB,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_fred_series (
    series_id   TEXT PRIMARY KEY,
    description TEXT,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_sp500_wiki (
    ticker TEXT PRIMARY KEY
);

-- ---------------------------------------------------------------------------
-- Time-series hypertables — price history (one row per ticker x date)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_yahoo_history (
    ticker      TEXT        NOT NULL,
    date        DATE        NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    adj_close   DOUBLE PRECISION,
    volume      BIGINT,
    dividend    DOUBLE PRECISION,
    split_ratio DOUBLE PRECISION,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_alpha_vantage_history (
    ticker            TEXT        NOT NULL,
    date              DATE        NOT NULL,
    open              DOUBLE PRECISION,
    high              DOUBLE PRECISION,
    low               DOUBLE PRECISION,
    close             DOUBLE PRECISION,
    adjusted_close    DOUBLE PRECISION,
    volume            BIGINT,
    dividend_amount   DOUBLE PRECISION,
    split_coefficient DOUBLE PRECISION,
    scraped_at        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_macrotrends_history (
    ticker      TEXT        NOT NULL,
    date        DATE        NOT NULL,
    adj_open    DOUBLE PRECISION,
    adj_high    DOUBLE PRECISION,
    adj_low     DOUBLE PRECISION,
    adj_close   DOUBLE PRECISION,
    volume      BIGINT,
    ma50        DOUBLE PRECISION,
    ma200       DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    market_cap  DOUBLE PRECISION,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_yahoo_daily (
    ticker                TEXT        NOT NULL,
    date                  DATE        NOT NULL,
    open                  DOUBLE PRECISION,
    high                  DOUBLE PRECISION,
    low                   DOUBLE PRECISION,
    close                 DOUBLE PRECISION,
    volume                BIGINT,
    change                DOUBLE PRECISION,
    change_pct            DOUBLE PRECISION,
    quote_type            TEXT,
    market_cap            DOUBLE PRECISION,
    total_assets          DOUBLE PRECISION,
    nav                   DOUBLE PRECISION,
    shares_outstanding    DOUBLE PRECISION,
    shares_float         DOUBLE PRECISION,
    shares_short          DOUBLE PRECISION,
    shares_short_ratio    DOUBLE PRECISION,
    shares_short_pct_float DOUBLE PRECISION,
    insiders_pct          DOUBLE PRECISION,
    institutions_pct      DOUBLE PRECISION,
    beta                  DOUBLE PRECISION,
    scraped_at            TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_eoddata_daily (
    ticker    TEXT        NOT NULL,
    date      DATE        NOT NULL,
    exchange  TEXT,
    open      DOUBLE PRECISION,
    high      DOUBLE PRECISION,
    low       DOUBLE PRECISION,
    close     DOUBLE PRECISION,
    volume    BIGINT,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date, exchange)
);

-- ---------------------------------------------------------------------------
-- Time-series — macro / sentiment / volume
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_fred (
    series_id   TEXT        NOT NULL,
    date        DATE        NOT NULL,
    value       DOUBLE PRECISION,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (series_id, date)
);

CREATE TABLE IF NOT EXISTS raw_short_finra (
    symbol             TEXT        NOT NULL,
    date               DATE        NOT NULL,
    short_volume       BIGINT,
    short_exempt_volume BIGINT,
    total_volume       BIGINT,
    market             TEXT,
    scraped_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, date, market)
);

CREATE TABLE IF NOT EXISTS raw_cpc (
    category        TEXT        NOT NULL,    -- total|index|etp|equity|vix|spx|oex
    date            DATE        NOT NULL,
    ratio           DOUBLE PRECISION,
    vol_call        BIGINT,
    vol_put         BIGINT,
    vol_total       BIGINT,
    oi_call         BIGINT,
    oi_put          BIGINT,
    oi_total        BIGINT,
    scraped_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (category, date)
);

-- ---------------------------------------------------------------------------
-- Earnings + fund flow
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_yahoo_earnings (
    earnings_week_monday DATE       NOT NULL,
    ticker               TEXT       NOT NULL,
    earnings_date        DATE,
    report_time          TEXT,                       -- 'before' | 'after'
    eps_avg              DOUBLE PRECISION,
    eps_low              DOUBLE PRECISION,
    eps_high             DOUBLE PRECISION,
    revenue_avg          DOUBLE PRECISION,
    revenue_low          DOUBLE PRECISION,
    revenue_high         DOUBLE PRECISION,
    scraped_at           TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (earnings_week_monday, ticker)
);

CREATE TABLE IF NOT EXISTS raw_etfdb_fundflow (
    ticker     TEXT        NOT NULL,
    date       DATE        NOT NULL,
    fundflow   DOUBLE PRECISION,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_etfcom_fundflow (
    ticker     TEXT        NOT NULL,
    date       DATE        NOT NULL,
    flows      JSONB,                       -- per-period flow breakdown
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS raw_etf_holdings (
    ticker     TEXT        NOT NULL,
    date       DATE        NOT NULL,
    name       TEXT,
    allocation DOUBLE PRECISION,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date, name)
);

-- ---------------------------------------------------------------------------
-- Snapshot tables (wide/site-native schemas kept as JSONB)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_finviz_daily (
    date       DATE        NOT NULL,
    ticker     TEXT        NOT NULL,
    sector     TEXT,
    industry   TEXT,
    market_cap TEXT,
    payload    JSONB,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS raw_bonds_bi (
    date      DATE        NOT NULL,
    bond_id   TEXT        NOT NULL,
    payload   JSONB,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (date, bond_id)
);

CREATE TABLE IF NOT EXISTS raw_bonds_finra (
    date       DATE        NOT NULL,
    cusip      TEXT        NOT NULL,
    payload    JSONB,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (date, cusip)
);

-- ---------------------------------------------------------------------------
-- Reconciled output tables (written by the reconcile job)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reconcile_price_history (
    ticker        TEXT        NOT NULL,
    date          DATE        NOT NULL,
    open          DOUBLE PRECISION,
    high          DOUBLE PRECISION,
    low           DOUBLE PRECISION,
    close         DOUBLE PRECISION,
    adj_open      DOUBLE PRECISION,
    adj_high      DOUBLE PRECISION,
    adj_low       DOUBLE PRECISION,
    adj_close     DOUBLE PRECISION,
    volume        BIGINT,
    dividend      DOUBLE PRECISION,
    split_ratio   DOUBLE PRECISION,
    split_factor  DOUBLE PRECISION,
    source_count  INT,
    sources       TEXT[],
    reconciled_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS reconcile_etf_daily (
    ticker            TEXT        NOT NULL,
    date              DATE        NOT NULL,
    prev_close        DOUBLE PRECISION,
    open              DOUBLE PRECISION,
    high              DOUBLE PRECISION,
    low               DOUBLE PRECISION,
    close             DOUBLE PRECISION,
    volume            BIGINT,
    market_cap        DOUBLE PRECISION,
    total_assets      DOUBLE PRECISION,
    nav               DOUBLE PRECISION,
    shares_outstanding DOUBLE PRECISION,
    fundflow          DOUBLE PRECISION,
    source_count      INT,
    sources           TEXT[],
    reconciled_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

-- ---------------------------------------------------------------------------
-- Convert time-series tables to hypertables
-- (create_hypertable is idempotent-safe if guarded; we use IF NOT EXISTS dim)
-- ---------------------------------------------------------------------------

SELECT create_hypertable('raw_yahoo_history',           'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_alpha_vantage_history',   'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_macrotrends_history',     'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_yahoo_daily',             'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_eoddata_daily',           'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_fred',                    'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_short_finra',             'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_cpc',                     'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_yahoo_earnings',          'earnings_week_monday', if_not_exists => TRUE);
SELECT create_hypertable('raw_etfdb_fundflow',          'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_etfcom_fundflow',         'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_etf_holdings',            'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_finviz_daily',            'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_bonds_bi',                'date', if_not_exists => TRUE);
SELECT create_hypertable('raw_bonds_finra',             'date', if_not_exists => TRUE);
SELECT create_hypertable('reconcile_price_history',     'date', if_not_exists => TRUE);
SELECT create_hypertable('reconcile_etf_daily',         'date', if_not_exists => TRUE);

-- ---------------------------------------------------------------------------
-- Compression policies — segment by ticker for fast per-ticker scans on
-- compressed chunks. Compress chunks older than 90 days.
-- ---------------------------------------------------------------------------

ALTER TABLE raw_yahoo_history         SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_alpha_vantage_history SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_macrotrends_history   SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_yahoo_daily           SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_eoddata_daily         SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_fred                  SET (timescaledb.compress, timescaledb.compress_segmentby = 'series_id');
ALTER TABLE raw_short_finra           SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
ALTER TABLE raw_cpc                   SET (timescaledb.compress, timescaledb.compress_segmentby = 'category');
ALTER TABLE raw_etfdb_fundflow        SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_etfcom_fundflow       SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE raw_finviz_daily          SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE reconcile_price_history   SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');
ALTER TABLE reconcile_etf_daily       SET (timescaledb.compress, timescaledb.compress_segmentby = 'ticker');

SELECT add_compression_policy('raw_yahoo_history',         INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_alpha_vantage_history', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_macrotrends_history',   INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_yahoo_daily',           INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_eoddata_daily',         INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_fred',                  INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_short_finra',           INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_cpc',                   INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_etfdb_fundflow',        INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_etfcom_fundflow',       INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('raw_finviz_daily',          INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('reconcile_price_history',   INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_compression_policy('reconcile_etf_daily',       INTERVAL '90 days', if_not_exists => TRUE);

-- ---------------------------------------------------------------------------
-- Continuous aggregate: latest close per ticker (for the dashboard chart)
-- Materialized every hour from the reconciled price history.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_latest_close
WITH (timescaledb.continuous) AS
SELECT ticker, date, close
FROM reconcile_price_history
WHERE close IS NOT NULL
WITH NO DATA;

SELECT add_continuous_aggregate_policy('cagg_latest_close',
    start_offset => INTERVAL '30 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);
