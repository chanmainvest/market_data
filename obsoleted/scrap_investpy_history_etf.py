#!/usr/bin/env python

import pandas as pd
import argparse
import sys
import investpy
import glob
import os
import datetime
import time

scrap_delay = 2

def main():
    parser = argparse.ArgumentParser(description='scrap yahoo earning')
    parser.add_argument('-output_dir', type=str, default='../stock_data_local/raw_history_investing_etf/', help='output directory')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    country = 'united states'
    etfs_dict = investpy.get_etfs_dict(country)

    today = datetime.datetime.now().strftime('%d/%m/%Y')
    for count,etf_row in enumerate(etfs_dict):
        if args.skip is not None:
            if count < args.skip:
                continue

        ticker = etf_row['symbol']
        print('downloading...', ticker, '-', count, '/', len(etfs_dict))
        try:
            df_etf = investpy.get_etf_historical_data(etf_row['name'],country,'1/1/1990',today)
            df_etf.to_csv(args.output_dir + ticker + '.csv')
        except Exception as e:
            print('FAIL -', e)
        time.sleep(scrap_delay)

    return 0

if __name__ == "__main__":
    sys.exit(main())

