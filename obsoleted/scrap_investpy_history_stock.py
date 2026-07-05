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
    parser.add_argument('-output_dir', type=str, default='../stock_data_local/raw_history_investing_stock/', help='output directory')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    country = 'united states'
    stocks_dict = investpy.get_stocks_dict(country)

    today = datetime.datetime.now().strftime('%d/%m/%Y')
    for count,stock_row in enumerate(stocks_dict):
        if args.skip is not None:
            if count < args.skip:
                continue

        ticker = stock_row['symbol']
        print('downloading...', ticker, '-', count, '/', len(stocks_dict))
        try:
            df_stock = investpy.get_stock_historical_data(ticker,country,'1/1/1990',today)
            try:
                df_dividend = investpy.get_stock_dividends(ticker,country)
                df_dividend.set_index('Date', inplace=True)
                df = pd.concat([df_stock, df_dividend], axis=1)
            except Exception as e:
                print(e)
                df = df_stock
            df.to_csv(args.output_dir + ticker + '.csv')
        except Exception as e:
            print(e)
        time.sleep(scrap_delay)

    return 0

if __name__ == "__main__":
    sys.exit(main())

