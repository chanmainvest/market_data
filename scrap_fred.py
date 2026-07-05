#!/usr/bin/env python

import argparse
import csv
import sys

from fredapi import Fred

def main():
    parser = argparse.ArgumentParser(description='scrap fred')
    parser.add_argument('-input', type=str, default='data_tickers/fred_stats.csv', help='input csv file list all tickers to scrap')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_fred/', help='prefix of the output file')
    parser.add_argument('-apikey', type=str, help='Fred API key')
    args = parser.parse_args()

    # scrap the data
    fred = Fred(api_key=args.apikey)
    with open(args.input) as csvfile:
        fredreader = csv.reader(csvfile, delimiter=',')
        next(fredreader)
        for row in fredreader:
            filename = args.output_prefix + row[0] + '.csv'
            print('Getting', row[0], '-', row[1])
            try:
                s = fred.get_series(row[0])
                s.to_csv(filename)

                # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
                import db
                import pandas as pd
                df_fred = s.reset_index()
                df_fred.columns = ['date', 'value']
                df_fred['series_id'] = row[0]
                db.upsert_df(df_fred, 'raw_fred', conflict_cols=['series_id', 'date'])
                # keep the series reference table fresh
                db.upsert_df(pd.DataFrame([{'series_id': row[0], 'description': row[1]}]),
                             'ref_fred_series', conflict_cols=['series_id'])
            except Exception as exc:
                print(f'failed: {exc}')

    return 0

if __name__ == "__main__":
    sys.exit(main())