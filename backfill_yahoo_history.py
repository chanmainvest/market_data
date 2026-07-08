#!/usr/bin/env python
"""Incremental backfill for raw_yahoo_history.

For each ticker already in the database, fetch only the gap between its
last-known date and today — not the full history (which is what
scrap_yahoo_history.py does with period='max'). This avoids re-downloading
40 years of data per ticker and dramatically cuts request volume, keeping
us under Yahoo's rate limit.

Uses the rotating SOCKS5 proxy pool (YAHOO_PROXY_HOSTS) + polite delays.

Run:
    MARKET_DATA_DB=1 YAHOO_PROXY_HOSTS=oc1.hevangel.com,oc2.hevangel.com,serv00 \
    uv run python backfill_yahoo_history.py [--batch N] [--delay 2]

Resume-safe: re-running skips tickers already up to date (within 3 days of
today).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests
import yfinance as yf
from sqlalchemy import text

# Ensure the scrapers dir is importable (scrap_utils, db).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrap_utils import init_proxy_pool, next_proxy, stop_proxy_pool  # noqa: E402
import db as writer  # noqa: E402

TODAY = date.today()
# A ticker is considered "current" if its last row is within this many days
# of today. Skips re-fetching on resume / same-day re-runs.
FRESH_DAYS = 3
# Default per-request delay (seconds). With 5 proxy IPs this yields ~5x the
# effective per-IP rate, but we stay polite regardless.
DEFAULT_DELAY = 2


def _load_ticker_state() -> list[tuple[str, str | None]]:
    """Return [(ticker, last_date_str_or_None)] for all tickers in the DB.

    Tickers with no existing data (None) get a full-history fetch; others
    get an incremental fetch from last_date+1.
    """
    eng = writer.engine()
    if eng is None:
        print("ERROR: MARKET_DATA_DB=1 required for backfill", file=sys.stderr)
        sys.exit(1)
    with eng.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT ticker, max(date)::text AS last_date
                FROM raw_yahoo_history
                GROUP BY ticker
                ORDER BY ticker
            """)
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _make_session(proxy: str | None) -> requests.Session | None:
    """Build a requests.Session routed through the SOCKS5 proxy, or None
    for direct connection. Modern yfinance (1.5+) takes ``session=``
    rather than ``proxy=``."""
    if not proxy:
        return None
    s = requests.Session()
    s.proxies.update({"http": proxy, "https": proxy})
    return s


def _fetch_gap(ticker: str, last_date: str | None, proxy: str | None) -> pd.DataFrame | None:
    """Fetch Yahoo history for ``ticker`` from ``last_date+1`` to today.

    If last_date is None (no existing data), fetch the full history.
    Returns a DataFrame with columns matching raw_yahoo_history, or None
    on failure / empty result.
    """
    if last_date is None:
        start = None
    else:
        # Start one day after the last known date.
        start = (pd.to_datetime(last_date) + timedelta(days=1)).date()

    # If we're already current, skip.
    if start is not None and (TODAY - start).days <= FRESH_DAYS:
        return None

    # Retry with backoff + proxy rotation on rate-limit (429).
    max_retries = 4
    backoff = 30
    for attempt in range(max_retries):
        session = _make_session(proxy)
        try:
            # Use Ticker.history() — yf.download() does an aggressive pre-flight
            # rate-limit check in yfinance 1.5+ that fails even when
            # Ticker.history() succeeds.
            yf_ticker = yf.Ticker(ticker, session=session)
            data = yf_ticker.history(
                start=str(start) if start else "1990-01-01",
                end=str(TODAY + timedelta(days=1)),  # end is exclusive
                auto_adjust=False,
                prepost=False,
                repair=True,
            )
            break  # success
        except Exception as exc:
            msg = str(exc)
            if "Too Many Requests" in msg or "Rate limited" in msg or "429" in msg:
                # Rotate to the next proxy and back off.
                print(f"  {ticker}: rate-limited (attempt {attempt+1}/{max_retries}), "
                      f"backing off {backoff}s and rotating proxy")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                proxy = next_proxy()
                continue
            print(f"  {ticker}: history failed ({exc})")
            return None
    else:
        print(f"  {ticker}: exhausted retries after rate-limiting")
        return None

    if data is None or data.empty:
        return None

    # Flatten MultiIndex columns (single-ticker download).
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Fetch dividends/splits from the same Ticker object (no extra request).
    try:
        dividends = yf_ticker.dividends
        splits = yf_ticker.splits
        if dividends is not None and not dividends.empty:
            data["Dividend"] = dividends.reindex(data.index).fillna(0.0)
        if splits is not None and not splits.empty:
            data["Split"] = splits.reindex(data.index).fillna(0.0)
    except Exception as exc:
        print(f"  {ticker}: dividend/split fetch failed ({exc})")

    out = data.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
        "Dividend": "dividend", "Split": "split_ratio",
    })
    out["ticker"] = ticker
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="incremental backfill of yahoo history")
    parser.add_argument("--batch", type=int, default=None,
                        help="process only the first N tickers (for chunked runs)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help="seconds between requests per ticker")
    parser.add_argument("--skip", type=int, default=0,
                        help="skip the first N tickers (for resuming)")
    parser.add_argument("--ticker", type=str, default=None,
                        help="backfill a single ticker (debugging)")
    args = parser.parse_args()

    if args.ticker:
        ticker_state = [(args.ticker.upper(), None)]
    else:
        ticker_state = _load_ticker_state()

    if args.skip:
        ticker_state = ticker_state[args.skip:]
    if args.batch:
        ticker_state = ticker_state[: args.batch]

    print(f"backfilling {len(ticker_state)} tickers (delay={args.delay}s)")
    print(f"today = {TODAY}")

    # Start the proxy pool.
    pool = init_proxy_pool()
    n_proxies = len(pool.urls) if pool else 0
    if n_proxies:
        print(f"using {n_proxies} proxy tunnels; effective per-IP delay ~= {args.delay * n_proxies:.1f}s")
    else:
        print("WARNING: no proxy tunnels — direct connect. Risk of 429 on large batches.")

    total_rows = 0
    skipped = 0
    failed = 0
    try:
        for i, (ticker, last_date) in enumerate(ticker_state, 1):
            # Skip tickers already current.
            if last_date is not None:
                last = pd.to_datetime(last_date).date()
                if (TODAY - last).days <= FRESH_DAYS:
                    skipped += 1
                    continue

            proxy = next_proxy()
            df = _fetch_gap(ticker, last_date, proxy)
            if df is None or df.empty:
                # Could be current (skipped inside _fetch_gap) or genuinely empty.
                if last_date and (TODAY - pd.to_datetime(last_date).date()).days <= FRESH_DAYS:
                    skipped += 1
                else:
                    failed += 1
                    print(f"  [{i}/{len(ticker_state)}] {ticker}: no data (last={last_date})")
            else:
                n = writer.upsert_df(df, "raw_yahoo_history", conflict_cols=["ticker", "date"])
                total_rows += n
                if i % 50 == 0 or i <= 3:
                    print(f"  [{i}/{len(ticker_state)}] {ticker}: +{n} rows (last={last_date}) "
                          f"total={total_rows} via {proxy or 'direct'}", flush=True)

            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\ninterrupted — partial progress committed")
    finally:
        stop_proxy_pool()

    print(f"\ndone: {total_rows} new rows, {skipped} already current, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
