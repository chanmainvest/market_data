#!/usr/bin/env python

import argparse
import datetime
import sys
import time

import bs4
import pandas as pd

from scrap_utils import *  # noqa: F401,F403

# -----------------------------------------------------------------
# hand crafted scrapper
# -----------------------------------------------------------------
finviz_url = 'https://finviz.com/screener.ashx?'
scrap_delay = 1

def get_stock_table(tab, filter, page):
    page_url = finviz_url + tab + filter + '&r=' + str((page - 1) * 20 + 1)
    print('getting page', page, 'url:', page_url)
    html = get_url(page_url)
    soup = bs4.BeautifulSoup(html, 'lxml')
    # The screener results table has class "screener-table" in current finviz
    # layout; fall back to the old positional index [16] if not found.
    stock_table = soup.find('table', class_='screener-table')
    if stock_table is None:
        tables = soup.find_all('table')
        if len(tables) <= 16:
            raise RuntimeError(
                f'finviz table layout changed: only {len(tables)} tables found on {page_url}'
            )
        stock_table = tables[16]
    return pd.read_html(str(stock_table), header=0, index_col=1)[0]

def scrap_finviz(filter, tab_list = None):
    # get the front page
    front_page = get_url(finviz_url + filter)

    # get the last page
    soup = bs4.BeautifulSoup(front_page, 'lxml')
    screener_pages = soup.find_all('a', {'class' : 'screener-pages'})
    last_page = int(screener_pages[-1].text)
    print('total pages:', last_page)

    if tab_list is None:
        tab_list = ['v=111&', 'v=121&', 'v=131&', 'v=141&', 'v=161&', 'v=171&',]
    df_pages = []
    for i in range(1,last_page+1):
        df_tabs = []
        for tab in tab_list:
            time.sleep(scrap_delay)
            df_tabs.append(get_stock_table(tab,filter,i))
        df_pages.append(pd.concat(df_tabs, axis=1))
    df_merged = pd.concat(df_pages)

    return df_merged

def main():
    parser = argparse.ArgumentParser(description='scrap finviz screener')
    parser.add_argument('-output', type=str, help='output file')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_finviz/finviz_', help='prefix of the output file')
    parser.add_argument('-use_bs4_scrapper', type=bool, default=True, help='Use my old bs4 scraper')
    parser.add_argument('-date', type=str, default=str(datetime.date.today()), help='Specify the date')
    parser.add_argument('-filter', type=str, action='append', help='filters apply to the screener')
    parser.add_argument('-tab', type=str, action='append', help='tabs to the scrap')
    parser.add_argument('-delay', type=int, help='delay in sec between each URL request')
    parser.add_argument('-drop_col', type=str, action='append', default=[], help='remove columns')
    args = parser.parse_args()

    if args.filter is None:
        args.filter = ['f=cap_microover', 'f=cap_microunder']
    if args.delay is not None:
        global scrap_delay
        scrap_delay = args.delay

    # check is the market closed today
    if is_market_close(args.date):
        print('The market is closed today')
        return

    if args.output is None:
        filename = args.output_prefix + args.date + '.csv'
    else:
        filename = args.output

    # scrap the data
    if args.use_bs4_scrapper:
        # use my old code
        df_filters = []
        for filter in args.filter:
            df_filters.append(scrap_finviz(filter, args.tab))
        df = pd.concat(df_filters)
    else:
        # use the modern finvizfinance package
        from finvizfinance.screener.overview import Overview

        screener = Overview()
        filters_dict = {}
        for f in args.filter:
            # filters come in like "f=cap_microover"; strip the prefix
            key = f[2:] if f.startswith('f=') else f
            filters_dict.setdefault('filters', []).append(key)
        screener.set_filter(filters=filters_dict.get('filters', []))
        df = screener.screener_view()

    df = df.loc[~df.index.duplicated(), ~df.columns.duplicated()]
    df.drop(columns=['No.']+args.drop_col, inplace=True, errors='ignore')
    df.insert(0, 'Date', args.date, True)
    df.to_csv(filename)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1).
    # finviz has ~70 site-native columns -> store as JSONB payload.
    import db
    indexed = {'Date', 'Ticker', 'Sector', 'Industry', 'Market Cap'}
    rows = []
    for _, r in df.iterrows():
        rec = {c: r[c] for c in ['Date', 'Ticker', 'Sector', 'Industry', 'Market Cap'] if c in r.index}
        for col in ['Date']:
            if col in rec:
                rec[col] = str(rec[col])
        rows.append(rec)
    payload_cols = [c for c in df.columns if c not in indexed]
    db.upsert_jsonb_rows('raw_finviz_daily', ['date', 'ticker'], payload_cols, rows)

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)

