#!/usr/bin/env python

import argparse
import glob
import os
import sys
import time

import pandas as pd
import yfinance as yf
from scrap_utils import init_proxy_pool, next_proxy, stop_proxy_pool

scrap_delay = 2


def main():
    parser = argparse.ArgumentParser(description='scrap yahoo history')
    parser.add_argument('-input_dir', type=str, help='input directory, use the latest file')
    parser.add_argument('-input_file', type=str, default='data_tickers/yahoo_indexes.csv', help='input file')
    parser.add_argument('-output_dir', type=str, default='../stock_data/raw_history_yahoo/', help='output directory')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    if args.input_dir is not None:
        list_of_files = glob.glob(args.input_dir + '/*')
        input_file = max(list_of_files, key=os.path.getctime)
    else:
        input_file = args.input_file

    df_input = pd.read_csv(input_file)
    df_input.set_index('Ticker', inplace=True)
    ticker_list = df_input.index

    # Start the rotating SOCKS5 proxy pool if YAHOO_PROXY_HOSTS is set.
    init_proxy_pool()
    try:
        for count, ticker in enumerate(ticker_list):
            if args.skip is not None and count < args.skip:
                continue
            print('downloading...' + ticker, '-', count)
            proxy = next_proxy()

            try:
                data = yf.download(
                    ticker,
                    period='max',
                    auto_adjust=False,
                    prepost=False,
                    repair=True,
                    threads=True,
                    proxy=proxy,
                )
            except Exception as exc:
                print(f'download failed ({exc}), retry after backoff')
                time.sleep(30)
                proxy = next_proxy()
                data = yf.download(
                    ticker,
                    period='max',
                    auto_adjust=False,
                    prepost=False,
                    repair=True,
                    threads=True,
                    proxy=proxy,
                )

            # Modern yfinance returns MultiIndex columns even for a single
            # ticker (e.g. ('Close', 'AAPL')). Flatten to plain column names so
            # the saved CSV stays clean and assignment of Dividend/Split works
            # against the OHLC index.
            if isinstance(data.columns, pd.MultiIndex):
                # Keep the price level; drop the (now-redundant) ticker level.
                data.columns = data.columns.get_level_values(0)

            try:
                yf_ticker = yf.Ticker(ticker, proxy=proxy)
            except Exception as exc:
                print(f'Ticker get failed ({exc}), retry after backoff')
                time.sleep(30)
                proxy = next_proxy()
                yf_ticker = yf.Ticker(ticker, proxy=proxy)

            try:
                dividends = yf_ticker.dividends
                splits = yf_ticker.splits
                # modern yfinance: dividends/splits are Series indexed by date,
                # or None/empty when none exist. Align into the OHLC frame.
                if dividends is not None and not dividends.empty:
                    data['Dividend'] = dividends.reindex(data.index).fillna(0.0)
                if splits is not None and not splits.empty:
                    data['Split'] = splits.reindex(data.index).fillna(0.0)
            except Exception as exc:
                print(f'dividend or split download failed: {exc}')

            data.to_csv(args.output_dir + ticker + '.csv')

            # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
            import db
            out = data.reset_index().rename(columns={
                'Adj Close': 'adj_close',
                'Dividend': 'dividend',
                'Split': 'split_ratio',
            })
            out['ticker'] = ticker
            db.upsert_df(out, 'raw_yahoo_history', conflict_cols=['ticker', 'date'])

            time.sleep(scrap_delay)
    finally:
        stop_proxy_pool()


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
