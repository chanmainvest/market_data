#!/usr/bin/env python

import pandas as pd
import numpy as np
import argparse
import datetime
import sys
from scrap_utils import *
import os
import itertools

def main():
    parser = argparse.ArgumentParser(description='clean up ETF daily data')
    parser.add_argument('-input', type=str, default='data_tickers/etfs_info.csv', help='input file')
    parser.add_argument('-date', type=str, default=str(datetime.date.today()), help='Specify the date')
    parser.add_argument('-output_dir', type=str, default='../stock_data/data_etf_daily/', help='output directory')
    args = parser.parse_args()

    source_list = {
        'Yahoo': 'raw_daily_yahoo/yahoo_',
        'Eoddata': 'raw_daily_eoddata/eoddata_',
        'Investing': 'raw_daily_investing_etf/investing_etf_',
    }

    date = args.date
    df_raw = {}
    for k,v in source_list.items():
        csv_file = f"../stock_data/{v}{date}.csv"
        if os.path.exists(csv_file):
            df_raw[k] = pd.read_csv(csv_file, index_col=0, parse_dates=True)
        else:
            print('file not found:', csv_file)

    # Create the final DataFrame
    fields = ['PrevClose', 'Open', 'High', 'Low', 'Close', 'Volume', 'MarketCap', 'TotalAssets', 'NAV', 'SharesOutstanding']
    sources = ['Data'] + list(df_raw.keys())
    columns = pd.MultiIndex.from_product([sources, fields], names=['Source','Fields'])
    df_input = pd.read_csv(args.input, comment='#', index_col=0)
    etf_list = sorted(df_input.index.to_list())
    df = pd.DataFrame(index=etf_list, columns=columns)
    df.index.name = 'Ticker'

    df_etf = {}
    if 'Yahoo' in df_raw:
        df_etf['Yahoo'] = df_raw['Yahoo'].loc[df_raw['Yahoo']['Type']=='EFT', ['Ticker','Open','High','Close','Volume','TotalAssets','NAV']]
        df_etf['Yahoo'].set_index('Ticker', inplace=True)
    if 'Eoddata' in df_raw:
        df_etf['Eoddata'] = df_raw['Eoddata'].loc[df_raw['Eoddata']['Symbol'].isin(etf_list), ['Symbol','Open','High','Low','Close','Volume']]
        df_etf['Eoddata'].set_index('Symbol', inplace=True)
        df_etf['Eoddata'] = df_etf['Eoddata'][~df_etf['Eoddata'].index.duplicated(keep='last')]

    if 'Investing' in df_raw:
        # investing.com export columns we care about: Symbol + Prev. Close
        invest_cols = [c for c in ['Symbol', 'Prev. Close'] if c in df_raw['Investing'].columns]
        if invest_cols:
            df_etf['Investing'] = df_raw['Investing'][invest_cols].copy()
            if 'Symbol' in df_etf['Investing'].columns:
                df_etf['Investing'].set_index('Symbol', inplace=True)

        if 'AlphaVantage' in df_raw:
            #df_raw['AlphaVantage'].drop(columns = ['adjusted_close'], inplace=True)
            df_raw['AlphaVantage'].rename(columns={
                'timestamp' : 'Date',
                'open' : 'Open',
                'high' : 'High',
                'low' : 'Low',
                'close' : 'Close',
                'volume' : 'Volume',
                'dividend_amount' : 'Dividend',
                'split_coefficient' : 'Split',
            }, inplace=True)
            df_raw['AlphaVantage']['SplitFactor'] = df_raw['AlphaVantage']['Split'].cumprod().shift(1, fill_value=1.0)
            df_raw['AlphaVantage']['AdjOpen'] = df_raw['AlphaVantage']['Open'] / df_raw['AlphaVantage']['SplitFactor']
            df_raw['AlphaVantage']['AdjHigh'] = df_raw['AlphaVantage']['High'] / df_raw['AlphaVantage']['SplitFactor']
            df_raw['AlphaVantage']['AdjLow'] = df_raw['AlphaVantage']['Low'] / df_raw['AlphaVantage']['SplitFactor']
            df_raw['AlphaVantage']['AdjClose'] = df_raw['AlphaVantage']['Close'] / df_raw['AlphaVantage']['SplitFactor']

        if 'Macrotrends' in df_raw:
            df_raw['Macrotrends']['SplitFactor'] = df_raw['Macrotrends']['Close'] / df_raw['Macrotrends']['AdjClose']
            df_raw['Macrotrends']['Split'] = df_raw['Macrotrends']['SplitFactor'].shift(1) / df_raw['Macrotrends']['SplitFactor']
            df_raw['Macrotrends']['Split'].fillna(1.0, inplace=True)
            df_raw['Macrotrends']['Dividend'] = np.nan
            df_raw['Macrotrends']['Open'] = df_raw['Macrotrends']['AdjOpen'] * df_raw['Macrotrends']['SplitFactor']
            df_raw['Macrotrends']['High'] = df_raw['Macrotrends']['AdjHigh'] * df_raw['Macrotrends']['SplitFactor']
            df_raw['Macrotrends']['Low'] = df_raw['Macrotrends']['AdjLow'] * df_raw['Macrotrends']['SplitFactor']

        # Copy raw to final DataFrame
        for field in fields:
            for source in df_raw.keys():
                df[(source, field)] = df_raw[source][field]

        # Merge and clean up raw data
        print('Merging Split')
        df_split_mode = df[itertools.product(df_raw.keys(),['Split'])].round(4).mode(axis=1)
        if len(df_split_mode.columns) > 2:
            print('Split - no majority:\n', df_split_mode[df_split_mode[2].notna()])
        df[('Data','Split')] = df_split_mode[0]
        df[('Data','SplitFactor')] = df[('Data','Split')][::-1].cumprod().shift(1, fill_value=1.0)

        # Fix the missing split
        for source in df_raw.keys():
            df_split_diff = (~ np.isclose(df[('Data', 'Split')],df[(source, 'Split')])) & df[(source, 'Split')].notna()
            if df_split_diff.any():
                print('Fixing split error for', source)
                if source == 'Macrotrends':
                    for field in ['Open', 'High', 'Low', 'Close']:
                        df[('Macrotrends','Adj'+field)] = df[('Macrotrends',field)] / df[('Data','SplitFactor')]

        # Merge columns
        for field in ['Open', 'High', 'Low', 'Close', 'AdjOpen', 'AdjHigh', 'AdjLow', 'AdjClose', 'Volume', 'Dividend']:
            print('Merging ', field)
            df_mode = df[itertools.product(df_raw.keys(),[field])].round(2).mode(axis=1)
            if len(df_mode.columns) > 2:
                print('No majority:\n', df_mode[df_mode[1].notna()])
                df_mode.loc[df_mode[1].notna(),0] = df_mode[df_mode[1].notna()].median(axis=1)
            df[('Data', field)] = df_mode[0]

        # Output CSV files — write one daily snapshot per ETF.
        os.makedirs(args.output_dir, exist_ok=True)
        for ticker in df.index:
            df_out = df.loc[[ticker], 'Data'].copy()
            fundflow_path = '../stock_data/temp/' + ticker + '.csv'
            if os.path.exists(fundflow_path):
                df_ff = pd.read_csv(fundflow_path, index_col=1,
                                    names=['File', 'Date', 'FundFlow'], parse_dates=True)
                df_ff = df_ff[~df_ff.index.duplicated()]
                df_out['FundFlow'] = df_ff['FundFlow'].reindex(df_out.index).iloc[:, 0] if df_out.shape[1] else None
            df_out.to_csv(args.output_dir + ticker + '.csv')

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
