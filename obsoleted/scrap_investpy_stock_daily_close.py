#!/usr/bin/env python

import pandas as pd
import argparse
import datetime
import time
import sys
import investpy

scrap_delay = 2

def main():
    parser = argparse.ArgumentParser(description='scrap investing.com daily close')
    parser.add_argument('-input_file', type=str, default='data_tickers/investing_stock_info.csv', help='input file')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_investing_stock/investing_stock_', help='prefix of the output file')
    parser.add_argument('-date', type=str, help='Specify the date')
    args = parser.parse_args()

    if args.date is None:
        scrap_date = datetime.date.today()
        args.date = str(scrap_date)

    filename = args.output_prefix + args.date + '.csv'
    df_input = pd.read_csv(args.input_file)

    info_list = []
    print('number of tickers:', len(df_input.index))
    for index,row in df_input.iterrows():
        print('downloading...', row['symbol'], row['country'], '-', index)
        try:
            info = investpy.get_stock_information(row['symbol'],row['country'])
            info_list.append(info)
        except:
            print('failed')
        time.sleep(scrap_delay)

    df = pd.concat(info_list)
    df['Date'] = args.date
    df.to_csv(filename)

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
