#!/usr/bin/env python
"""Download end-of-day data from eoddata.com.

Rewritten to use Playwright (Selenium/PhantomJS are discontinued).
"""

import argparse
import datetime
import sys

import pandas as pd
import requests

import scrap_utils
from scrap_utils import *  # noqa: F401,F403


def main():
    parser = argparse.ArgumentParser(description='scrap all etf')
    parser.add_argument('-use_firefox', action='store_true', help='Use firefox browser')
    parser.add_argument('-use_headless', action='store_true', help='Run browser headless')
    parser.add_argument('-username', type=str, help='Username')
    parser.add_argument('-password', type=str, help='Password')
    parser.add_argument('-delay', type=int, default=1, help='delay in sec between each URL request')
    parser.add_argument('-date', type=str, help='Specify the date to download')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_daily_eoddata/eoddata_', help='prefix of the output file')
    parser.add_argument('-bin', type=str, help='(ignored) kept for CLI compatibility')
    args = parser.parse_args()

    if args.date is None:
        scrap_date = datetime.datetime.today()
    else:
        scrap_date = datetime.datetime.strptime(args.date, '%Y-%m-%d')

    if not args.username or not args.password:
        print('ERROR: -username and -password are required to log in to eoddata.com', file=sys.stderr)
        return 1

    # launch browser
    scrap_utils.use_firefox = args.use_firefox
    scrap_utils.use_firefox_headless = args.use_headless or True
    page = get_driver()
    page.goto('http://www.eoddata.com')

    # login (ASP.NET WebForms field IDs — fragile but unchanged for years)
    try:
        page.locator('#ctl00_cph1_lg1_txtEmail').fill(args.username)
        page.locator('#ctl00_cph1_lg1_txtPassword').fill(args.password)
        page.locator('#ctl00_cph1_lg1_btnLogin').click()
    except Exception as exc:
        print(f'login failed (the page DOM may have changed): {exc}', file=sys.stderr)
        return 1

    page.goto('http://www.eoddata.com/download.aspx')
    try:
        page.locator('#cboxClose').first.click(timeout=3000)
    except Exception:
        pass  # overlay may not be present

    # download CSV for each exchange using a requests session seeded with cookies
    exchange_list = ['INDEX', 'AMEX', 'NYSE', 'NASDAQ', 'OTCBB']
    for exchange in exchange_list:
        print('download...', exchange)
        try:
            page.locator('#ctl00_cph1_d1_cboExchange').select_option(exchange)
        except Exception as exc:
            print(f'could not select exchange {exchange}: {exc}', file=sys.stderr)
            continue

        date_label = scrap_date.strftime('%b %d %Y').lstrip('0').replace(' 0', ' ')
        # The site formats links as e.g. "Jun 1 2024"; build a tolerant locator.
        try:
            download_link = page.get_by_text(date_label, exact=False).first
            download_url = download_link.get_attribute('href')
        except Exception as exc:
            print(f'could not find download link for {exchange} on {date_label}: {exc}', file=sys.stderr)
            continue
        if download_url is None:
            print(f'no href for {exchange} on {date_label}', file=sys.stderr)
            continue

        session = requests.Session()
        for cookie in scrap_utils._browser_ctx[2].cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        response = session.get(download_url)
        out_path = args.output_prefix + exchange + '_' + str(scrap_date.date()) + '.csv'
        with open(out_path, 'wb') as f:
            f.write(response.content)

    close_driver()

    # merge csv
    df_exchange_list = []
    for exchange in exchange_list:
        try:
            df_exchange = pd.read_csv(args.output_prefix + exchange + '_' + str(scrap_date.date()) + '.csv')
        except FileNotFoundError:
            print(f'skipping {exchange}: file not downloaded')
            continue
        df_exchange['Exchange'] = exchange
        df_exchange_list.append(df_exchange)
    if not df_exchange_list:
        print('no exchanges downloaded; nothing to merge', file=sys.stderr)
        return 1
    df = pd.concat(df_exchange_list, ignore_index=True)
    df.to_csv(args.output_prefix + str(scrap_date.date()) + '.csv', index=False)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    out = df.rename(columns={'Symbol': 'ticker'})
    out['date'] = str(scrap_date.date())
    db.upsert_df(out, 'raw_eoddata_daily', conflict_cols=['ticker', 'date', 'exchange'])


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
