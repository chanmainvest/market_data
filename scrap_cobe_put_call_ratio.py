#!/usr/bin/env python

import argparse
import datetime
import sys

import bs4
import pandas as pd

from scrap_utils import *  # noqa: F401,F403

# -----------------------------------------------------------------
# hand crafted scrapper
# -----------------------------------------------------------------
cobe_url = 'https://markets.cboe.com/us/options/market_statistics/daily/'
scrap_delay = 1

def get_cpc(scrap_date = None):
    page_url = cobe_url
    if scrap_date is not None:
        page_url += '?dt=' + scrap_date
    print('scraping...', page_url)
    page = get_url(page_url)
    soup = bs4.BeautifulSoup(page, 'lxml')

    page_date = soup.find('h3').text.split(',',1)[1][1:]
    scrap_page_date = str(datetime.datetime.strptime(page_date,'%B %d, %Y').date())
    if scrap_page_date is not None:
        if scrap_date != scrap_page_date:
            return None

    tables = soup.find_all('table')

    df = pd.DataFrame(index=['total', 'index', 'etp', 'equity', 'vix', 'spx', 'oex'],
                      columns=['Ratio', 'VolumeCall', 'VolumePut', 'VolumeTotal',
                               'OpenInterestCall','OpenInterestPut','OpenInterestTotal'])

    df_tables = pd.read_html(str(tables), header=0)
    df['Ratio'] = df_tables[0].iloc[:,1].to_list()
    for i in range(7):
        df.iloc[i, 1:4] = df_tables[i+1].iloc[1, 1:].to_list()
        df.iloc[i, 4:7] = df_tables[i+1].iloc[2, 1:].to_list()

    return df

def main():
    parser = argparse.ArgumentParser(description='scrap finviz screener')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_cpc/cpc_', help='prefix of the output file')
    parser.add_argument('-date', type=str, default=str(datetime.date.today()), help='Specify the date')
    parser.add_argument('-start_date', type=str, help='Specify the date')
    parser.add_argument('-end_date', type=str, help='Specify the date')
    args = parser.parse_args()

    if args.start_date is not None:
        if args.end_date is None:
            args.end_date = args.date
        date_list = list([str(d.date()) for d in pd.bdate_range(args.start_date, args.end_date)])
    else:
        date_list = [args.date]

    for d in date_list:
        print('date:', d)

        # check is the market closed today
        if is_market_close(d):
            print('The market is closed today')
            continue

        # update the CSV data file
        df = get_cpc(d)
        if df is not None:
            df.insert(0, 'Date', d, True)
            for index in df.index:
                df.loc[[index]].to_csv('../stock_data/data_cpc/'+index+'.csv',header=False,index=False,mode='a')

            # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
            import db
            df.index.name = 'category'
            out = df.reset_index()
            db.upsert_df(out, 'raw_cpc', conflict_cols=['category', 'date'])


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)

