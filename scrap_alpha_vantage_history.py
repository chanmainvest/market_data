#!/usr/bin/env python

import argparse
import os
import sys
import time

import pandas as pd
import requests

scrap_delay = 2


def main():
    parser = argparse.ArgumentParser(description='scrap alpha vantage history')
    parser.add_argument('-api_key_file', type=str, default='../hevangel-com/api_keys/alpha_vantage.txt', help='API key file')
    parser.add_argument('-input_file', type=str, action='append', help='input file')
    parser.add_argument('-output_dir', type=str, default='../stock_data/raw_history_alpha_vantage/', help='output directory')
    parser.add_argument('-function', type=str, default='TIME_SERIES_DAILY_ADJUSTED', help='API function')
    parser.add_argument('-interval', type=str, default='1min', help='intraday interval (only used by INTRADAY functions)')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    if args.input_file is None:
        args.input_file = ['data_tickers/all_stocks.csv']

    # Read Alpha Vantage API keys (one per line). The old code called
    # f.readline() inside `for line in f`, which double-read the file and
    # silently skipped every other key.
    api_key_list = []
    with open(args.api_key_file, 'r') as f:
        for line in f:
            key = line.strip()
            if key:
                api_key_list.append(key)
    if not api_key_list:
        print('ERROR: no API keys found in', args.api_key_file, file=sys.stderr)
        return 1

    # Read input ticker list
    df_input_list = []
    for input_file in args.input_file:
        df_input_list.append(pd.read_csv(input_file))
    df_input = pd.concat(df_input_list, sort=False)
    ticker_list = df_input['Ticker'].to_list()

    os.makedirs(args.output_dir, exist_ok=True)

    for count, ticker in enumerate(ticker_list):
        if args.skip is not None and count < args.skip:
            continue
        print('downloading...', ticker, '-', count)
        api_key = api_key_list[count % len(api_key_list)]

        # Build URL. If the function is intraday, append the interval param.
        function_param = args.function
        url = (
            'https://www.alphavantage.co/query?function=' + function_param
            + '&symbol=' + ticker
            + '&apikey=' + api_key
            + '&outputsize=full&datatype=csv'
        )
        if function_param.startswith('TIME_SERIES_INTRADAY'):
            url += '&interval=' + args.interval

        out_path = os.path.join(args.output_dir, ticker + '.csv')
        download_ok = False
        max_retry = 3
        for retry in range(max_retry):
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                with open(out_path, 'wb') as fh:
                    fh.write(response.content)
                download_ok = True
            except Exception as exc:
                print(f'download failed ({exc}), retry: {retry}')
                time.sleep((retry + 1) * 60)
            if download_ok:
                break

        # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
        if download_ok:
            try:
                import pandas as pd
                import db
                df_av = pd.read_csv(out_path)
                df_av = df_av.rename(columns={'timestamp': 'date'})
                df_av['ticker'] = ticker
                db.upsert_df(df_av, 'raw_alpha_vantage_history', conflict_cols=['ticker', 'date'])
            except Exception as exc:
                print(f'db write skipped: {exc}')

        time.sleep(scrap_delay)


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
