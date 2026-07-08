#!/usr/bin/env python

import yahooquery as yq
import pandas as pd
import argparse
import datetime
import time
import sys
from scrap_utils import *

scrap_delay = 1

def main():
    parser = argparse.ArgumentParser(description='scrap yahoo earning')
    parser.add_argument('-input_file', type=str, action='append', help='input file')
    parser.add_argument('-output', type=str, help='output file')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_yahoo/yahoo_', help='prefix of the output file')
    parser.add_argument('-date', type=str, default=str(datetime.date.today()), help='Specify the date')
    args = parser.parse_args()

    if args.input_file == None:
        args.input_file = [
            'data_tickers/yahoo_indexes.csv',
            'data_tickers/all_stocks.csv',
            'data_tickers/all_etfs.csv'
        ]

    if args.output is None:
        filename = args.output_prefix + args.date + '.csv'
    else:
        filename = args.output

    # run input files
    df_input_list = []
    for input_file in args.input_file:
        df_input_list.append(pd.read_csv(input_file))
    df_input = pd.concat(df_input_list)

    ticker_list = df_input['Ticker'].to_list()
    columns = {
        'price' : {
            'regularMarketOpen'             : 'Open',
            'regularMarketDayHigh'          : 'High',
            'regularMarketDayLow'           : 'Low',
            'regularMarketPrice'            : 'Close',
            'regularMarketVolume'           : 'Volume',
            'regularMarketChange'           : 'Change',
            'regularMarketChangePercent'    : 'ChangePercent',
            'quoteType'                     : 'Type',
        },
        'summary_detail' : {
            'marketCap'                     : 'MarketCap',
            'totalAssets'                   : 'TotalAssets',
            'navPrice'                      : 'NAV',
        },
        'key_stats' : {
            'floatShares'                   : 'SharesFloat',
            'sharesOutstanding'             : 'SharesOutstanding',
            'sharesShort'                   : 'SharesShort',
            'shortRatio'                    : 'SharesShortRatio',
            'shortPercentOfFloat'           : 'SharesShortPercentOfFloat',
            'heldPercentInsiders'           : 'SharesInsidersPercent',
            'heldPercentInstitutions'       : 'SharesInstitutionsPercent',
            'beta'                          : 'Beta'
        }
    }

    def _safe_get(prop, tk, key):
        """Return prop[tk][key] or None. yahooquery properties can be a dict
        keyed by symbol, a dict of {symbol: error_string}, or None."""
        if not isinstance(prop, dict):
            return None
        entry = prop.get(tk)
        if not isinstance(entry, dict):
            return None
        return entry.get(key)

    # Start the rotating SOCKS5 proxy pool if YAHOO_PROXY_HOSTS is set.
    # Each yq.Ticker construction will pick up the next egress IP via
    # next_proxy(), distributing requests to avoid Yahoo's per-IP 429s.
    init_proxy_pool()
    try:
        ticker_dict_list = []
        print('number of tickers:', len(ticker_list))
        for count, ticker in enumerate(ticker_list):
            print('downloading...', ticker, '-', count)
            try:
                proxy = next_proxy()
                yticker = yq.Ticker(ticker, proxy=proxy) if proxy else yq.Ticker(ticker)
                ticker_dict = {'Ticker': ticker}
                for module, module_dict in columns.items():
                    ymodule = getattr(yticker, module, None)
                    for ycol, col in module_dict.items():
                        value = _safe_get(ymodule, ticker, ycol)
                        if value is not None:
                            ticker_dict[col] = value
                ticker_dict_list.append(ticker_dict)
            except Exception as exc:
                print(f'Error, skip {ticker}: {exc}')

            time.sleep(scrap_delay)
    finally:
        stop_proxy_pool()

    df = pd.DataFrame(ticker_dict_list)
    df['Date'] = args.date
    df.to_csv(filename)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    db.upsert_df(df, 'raw_yahoo_daily', conflict_cols=['ticker', 'date'])

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
