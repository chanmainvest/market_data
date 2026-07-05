#!/usr/bin/env python
"""Scrape historical price, split, and market-cap data from macrotrends.net.

The original code used brittle positional script indexes (``[8]``, ``[4]``,
``[13]``); those break whenever the page layout shifts. We now search all
``<script>`` tags for the data array via regex.
"""

import argparse
import os
import re
import sys

import bs4
import pandas as pd

from scrap_utils import *  # noqa: F401,F403

scrap_delay = 2


def _extract_data_array(html, var_name):
    """Search every <script> for ``var_name = [{...}];`` and return the
    captured inner string, or None."""
    soup = bs4.BeautifulSoup(html, 'lxml')
    pattern = re.compile(re.escape(var_name) + r'\s*=\s*\[{(.*?)}\];', re.S)
    for script in soup.find_all('script'):
        match = pattern.search(str(script))
        if match:
            return match.group(1)
    return None


def _parse_rows(data_str):
    """Parse ``"k":"v","k2":"v2"`` rows into a list of value lists."""
    rows = []
    for row in data_str.split('},{'):
        tokens = row.split('","')
        values = []
        for token in tokens:
            parts = token.split(':"')
            values.append(parts[1].replace('"', '') if len(parts) > 1 else '')
        rows.append(values)
    return rows


def main():
    parser = argparse.ArgumentParser(description='scrap history from macrotrends')
    parser.add_argument('-input_file', type=str, default='data_tickers/all_tickers.csv', help='input file')
    parser.add_argument('-output_dir', type=str, default='../stock_data/raw_history_macrotrends/', help='output directory')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    df_input = pd.read_csv(args.input_file)
    df_input.set_index('Ticker', inplace=True)

    for count, ticker in enumerate(df_input.index):
        if args.skip is not None and count < args.skip:
            continue
        print('downloading...' + ticker, '-', count)
        filename = args.output_dir + ticker + '.csv'
        df = None

        # price history
        price_url = 'https://www.macrotrends.net/assets/php/stock_price_history.php?t=' + ticker
        price_page = get_url(price_url)
        if price_page:
            price_data = _extract_data_array(price_page, 'dataDaily')
            if price_data:
                price_rows = _parse_rows(price_data)
                n_cols = len(price_rows[0]) if price_rows else 0
                columns = ['Date', 'AdjOpen', 'AdjHigh', 'AdjLow', 'AdjClose', 'Volume', 'MA50', 'MA200']
                df = pd.DataFrame(price_rows, columns=columns[:n_cols])
                df.set_index('Date', inplace=True)

        # split history
        split_url = 'https://www.macrotrends.net/assets/php/stock_splits.php?t=' + ticker
        split_page = get_url(split_url)
        if split_page:
            split_data = _extract_data_array(split_page, 'dataDaily')
            if split_data and df is not None:
                split_rows = _parse_rows(split_data)
                df_split = pd.DataFrame(split_rows, columns=['Date', 'Close'])
                df_split.set_index('Date', inplace=True)
                df['Close'] = df_split['Close']

        # market cap history
        mktcap_url = 'https://www.macrotrends.net/assets/php/market_cap.php?t=' + ticker
        mktcap_page = get_url(mktcap_url)
        if mktcap_page:
            mktcap_data = _extract_data_array(mktcap_page, 'chartData')
            if mktcap_data and df is not None:
                mktcap_rows = _parse_rows(mktcap_data)
                df_mktcap = pd.DataFrame(mktcap_rows, columns=['Date', 'MarketCap'])
                df_mktcap.set_index('Date', inplace=True)
                df['MarketCap'] = df_mktcap['MarketCap']

        if df is not None:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            df.to_csv(filename)

            # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
            import db
            out = df.reset_index()
            out['ticker'] = ticker
            db.upsert_df(out, 'raw_macrotrends_history', conflict_cols=['ticker', 'date'])

        # time.sleep(scrap_delay)


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
