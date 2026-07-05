# Obsoleted scripts

These files are retired and no longer run on the modern stack:

- **`scrap_investpy_*.py` (6 files)** — depended on `investpy`, which was
  officially discontinued in 2022 after Investing.com blocked the library's
  requests and issued takedown notices. There is no maintained successor
  package; the underlying endpoints return HTTP 429/403 to scripted clients.
- **`alpha_vantage_test.py`** — throwaway test fragment containing a
  hard-coded API key. Replaced by the maintained `scrap_alpha_vantage_history.py`.
- **`Jenkinsfile_daily_investing_etf` / `Jenkinsfile_daily_investing_stock`** —
  Jenkins pipelines that only ran the now-retired investpy scrapers.
- **`Jenkinsfile_debug`** — debug pipeline that also invoked an investpy scraper.

These files are kept for historical reference only. They are NOT installed by
the project and will not import under Python 3.11+ with the current
dependency set.
