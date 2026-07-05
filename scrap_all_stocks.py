#!/usr/bin/env python

import pandas as pd
import argparse
import sys
from scrap_utils import *

scrap_delay = 1

def get_index_components(index):
    page = get_url('https://www.slickcharts.com/'+index)
    soup = bs4.BeautifulSoup(page, 'lxml')
    stock_table = soup.find_all('table')
    return pd.read_html(str(stock_table), header=0, index_col=2)[0]

def main():
    parser = argparse.ArgumentParser(description='scrap all stock list')
    parser.add_argument('-input', type=str, help='input finviz daily file')
    parser.add_argument('-output', default='data_tickers/all_stocks.csv', type=str, help='output file')
    args = parser.parse_args()

    # read input file
    if args.input is None:
        print('ERROR: -input finviz daily file is required', file=sys.stderr)
        return 1
    df_input = pd.read_csv(args.input)

    # read existing output file
    df_old = pd.read_csv(args.output)

    # Ticker
    df = df_input[['Ticker']]

    # Check new and delisted tickers
    old_tickers = set(df_old['Ticker'].to_list())
    new_tickers = set(df['Ticker'].to_list())

    print('New tickers:', new_tickers - old_tickers)
    print('Delisted tickers:', old_tickers - new_tickers)

    df.set_index('Ticker', inplace=True)
    index_list = ['nasdaq100', 'sp500', 'dowjones']
    for index in index_list:
        df_index = get_index_components(index)
        df.insert(len(df.columns), index, df_index['Weight'])

    df.to_csv(args.output)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    out = df.reset_index()
    out = out.rename(columns={'nasdaq100': 'w_nasdaq100', 'sp500': 'w_sp500', 'dowjones': 'w_dowjones'})
    out['type'] = 'stock'
    db.upsert_df(out, 'ref_ticker', conflict_cols=['ticker'])

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
