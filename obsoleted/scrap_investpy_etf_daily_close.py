#!/usr/bin/env python

import requests
import bs4
import pandas as pd
import argparse
import datetime
import time
import sys
import investpy
import scrap_utils
scrap_delay = 2

def main():
    parser = argparse.ArgumentParser(description='scrap investing.com daily close')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_investing_etf/investing_etf_', help='prefix of the output file')
    parser.add_argument('-date', type=str, help='Specify the date')
    args = parser.parse_args()

    if args.date is None:
        scrap_date = datetime.date.today()
        args.date = str(scrap_date)

    # get ETF overview
    page = scrap_utils.get_url('https://www.investing.com/etfs/usa-etfs?&issuer_filter=0')
    soup = bs4.BeautifulSoup(page, 'lxml')
    df_overview = pd.read_html(str(soup.find('table')), header=0, index_col=2)[0]
    df_overview.drop(columns=['Unnamed: 0', 'Unnamed: 7'], inplace=True)

    last_trade_time = df_overview.iloc[0]['Time']
    df_overview_traded = df_overview[df_overview['Time'] == last_trade_time]

    # get ETF list
    etf_info_list = []
    get_etfs_list = investpy.etfs.get_etfs('united states')

    print('number of traded tickers:', len(df_overview_traded.index), '/', len(get_etfs_list.index))
    count = 0

    for index,row in get_etfs_list.iterrows():
        print('downloading...', row['symbol'], '-', count)
        try:
            etf_info = investpy.get_etf_information(row['name'],'united states')
            etf_info['Symbol'] = row['symbol']

            etf_info_list.append(etf_info)
            time.sleep(scrap_delay)
        except:
            print('failed')
        count += 1

    df_etf_info = pd.concat(etf_info_list)
    df_etf_info.set_index('Symbol', inplace=True)

    df = df_etf_info.join(df_overview_traded, how='left')
    df['Date'] = args.date
    filename = args.output_prefix + args.date + '.csv'
    df.to_csv(filename)

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
