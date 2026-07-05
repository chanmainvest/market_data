#!/usr/bin/env python

import requests
import bs4
import pandas as pd
import argparse
import datetime
import time
import sys
import math
import re
from io import StringIO
from scrap_utils import *

# -----------------------------------------------------------------
# hand crafted scrapper
# -----------------------------------------------------------------
bonds_url = 'https://markets.businessinsider.com/bonds/finder?borrower=&maturity=&yield=&bondtype=6,7,8,19&coupon=&currency=333&rating=&country=18'
scrap_delay = 10

def get_bonds_table(page):
    page_url = bonds_url + '&p=' + str(page)
    print('getting page', page)
    page = get_url(page_url)
    soup = bs4.BeautifulSoup(page, 'lxml')
    bond_table = soup.find('table')
    return pd.read_html(str(bond_table), header=0, index_col=1)[0]

def main():
    parser = argparse.ArgumentParser(description='scrap bond yields from business insider')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_bonds_bi/bonds_', help='prefix of the output file')
    parser.add_argument('-date', type=str, default=str(datetime.date.today()), help='Specify the date')
    parser.add_argument('-output', type=str, help='output file')
    args = parser.parse_args()

    # get the front page
    front_page = get_url(bonds_url)

    # get the number of search result
    soup = bs4.BeautifulSoup(front_page, 'lxml')
    search_results = soup.find(id='bond-searchresults-container').find('h2')
    results = int(re.sub(' Results.*\t', '', re.sub('\r\n.*\(', '', search_results.text)).replace(',', ''))

    print('results:', results)

    filename = args.output_prefix + args.date + '.csv'

    df_pages = []
    for page in range(1,math.ceil(results/20)+1):
        df_pages.append(get_bonds_table(page))
        time.sleep(scrap_delay)
    df = pd.concat(df_pages)
    df.to_csv(filename)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    rows = []
    bond_id_col = df.index.name or 'bond_id'
    for idx, r in df.iterrows():
        rec = {'date': args.date, 'bond_id': str(idx)}
        for c in df.columns:
            rec[c] = r[c]
        rows.append(rec)
    db.upsert_jsonb_rows('raw_bonds_bi', ['date', 'bond_id'], list(df.columns), rows)

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)

