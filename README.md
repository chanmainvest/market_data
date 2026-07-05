# Stock scraper

Scrape stock, ETF, bond, and macro data from public web sources.

## Sources

| Scraper | Source | Library |
|---------|--------|---------|
| `scrap_yahoo_daily_close.py` | Yahoo Finance | `yahooquery` |
| `scrap_yahoo_history.py` | Yahoo Finance | `yfinance` |
| `scrap_yahoo_earning_calendar.py` | Yahoo Finance | `yfinance` |
| `scrap_alpha_vantage_history.py` | Alpha Vantage | REST API (`requests`) |
| `scrap_fred.py` | FRED (St. Louis Fed) | `fredapi` |
| `scrap_finviz_screener.py` | Finviz | `finvizfinance` / bs4 |
| `scrap_cobe_put_call_ratio.py` | CBOE | bs4 |
| `scrap_macrotrends_history.py` | Macrotrends | bs4 |
| `scrap_bonds_bi.py` | Business Insider | bs4 |
| `scrap_bonds_finra.py` | FINRA / Morningstar | Playwright |
| `scrap_short_finra.py` | FINRA RegSHO | `requests` |
| `scrap_eoddata.py` | eoddata.com | Playwright |
| `scrap_etf_info.py` | etfdb.com / etf.com | Playwright |
| `scrap_etfcom_fundflow.py` | etf.com | `cloudscraper` |
| `scrap_all_stocks.py` | slickcharts | bs4 |
| `scrap_sp500_wiki.py` | Wikipedia | `pandas.read_html` |

The `investpy`-based scrapers (Investing.com) were retired in 2022 and live
under [`obsoleted/`](obsoleted/README.md).

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# install dependencies into .venv
uv sync

# install the headless browser for the Playwright-based scrapers
uv run playwright install firefox

# run a scraper
uv run python scrap_yahoo_daily_close.py
```

There is no installable package — every script is standalone and shares
helpers from `scrap_utils.py`.

## Alpha Vantage note

The free Alpha Vantage tier allows 5 API calls/minute and 500 calls/day.
`scrap_alpha_vantage_history.py` reads multiple keys from a file
(one per line) and rotates them to work around the daily limit.
