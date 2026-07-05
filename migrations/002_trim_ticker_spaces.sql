-- 002_trim_ticker_spaces.sql
-- In-place trim of leading/trailing whitespace on ticker columns.
-- Idempotent: re-running is a no-op once tickers are clean.
--
-- These updates touch every row, so they're slow on the 25M-row hypertables.
-- Run during a maintenance window. Each UPDATE is a separate statement so a
-- failure on one table doesn't roll back the others.

BEGIN;

UPDATE raw_yahoo_history         SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_yahoo_daily           SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_alpha_vantage_history SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_macrotrends_history   SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_eoddata_daily         SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_etfdb_fundflow        SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_etfcom_fundflow       SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_etf_holdings          SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_finviz_daily          SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE raw_short_finra           SET symbol = btrim(symbol) WHERE symbol != btrim(symbol);
UPDATE raw_yahoo_earnings        SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);

-- Reference tables
UPDATE ref_ticker        SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE ref_etfdb_info    SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE ref_etfcom_info   SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE ref_sp500_wiki    SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);

-- Reconciled output
UPDATE reconcile_price_history SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);
UPDATE reconcile_etf_daily     SET ticker = btrim(ticker) WHERE ticker != btrim(ticker);

COMMIT;

-- Refresh planner statistics so approximate row counts and query plans
-- stay accurate after the bulk updates.
ANALYZE;
