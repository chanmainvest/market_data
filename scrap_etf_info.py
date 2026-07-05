#!/usr/bin/env python
"""Scrape ETF info and lists from etfdb.com and etf.com.

Rewritten to use Playwright (Selenium/PhantomJS are discontinued).
"""

import argparse
import datetime
import sys
import time

import bs4
import pandas as pd

import scrap_utils
from scrap_utils import *  # noqa: F401,F403

# -----------------------------------------------------------------
# hand crafted scrapper
# -----------------------------------------------------------------
etfdb_url = 'https://etfdb.com/etf/'
etfcom_url = 'https://www.etf.com/'


def etfcom_click_understand_button():
    page = get_driver()
    try:
        page.get_by_text('I Understand', exact=True).first.click(timeout=3000)
    except Exception:
        pass


def get_etfcom_info(ticker, output_etfcom_holdings=None):
    page_url = etfcom_url + ticker
    page = get_driver()
    page.goto(page_url)
    etfcom_click_understand_button()
    try:
        viewall = page.locator('.viewAll').first
        page.set_viewport_size({'width': 1280, 'height': 1024})
        viewall.click(timeout=3000)
        time.sleep(0.5)
    except Exception:
        pass
    html = page.content()
    soup = bs4.BeautifulSoup(html, 'lxml')
    row_dict = {'Ticker': ticker}
    h1 = soup.find('h1')
    if h1 is None:
        return row_dict
    next_span = h1.find_next('span')
    row_dict['Description'] = next_span.text if next_span else ''
    for id_ in ['fundSummaryData', 'fundPortfolioData', 'fundIndexData']:
        id_tag = soup.find(id=id_)
        if id_tag is None:
            continue
        for div in id_tag.find_all('div', class_='rowText'):
            label = div.find('label')
            if label is not None and label.find_next_sibling() is not None:
                row_dict[label.text.replace('\n', '')] = label.find_next_sibling().text.replace('\n', '')
    if output_etfcom_holdings:
        cbox = soup.find(id='cboxOverlay')
        if cbox is not None:
            holdings_table = cbox.find_next('table')
            if holdings_table is not None:
                df_holdings = pd.read_html(str(holdings_table))[0]
                df_holdings.columns = ['Name', 'Allocation']
                df_holdings.to_csv(output_etfcom_holdings + ticker + '.csv')
                # dual-write (no-op unless MARKET_DATA_DB=1)
                import datetime as _dt
                import db
                out = df_holdings.rename(columns={'Name': 'name', 'Allocation': 'allocation'})
                out['ticker'] = ticker
                out['date'] = str(_dt.date.today())
                db.upsert_df(out, 'raw_etf_holdings', conflict_cols=['ticker', 'date', 'name'])
    return row_dict


def get_etfdb_info(ticker, output_etfdb_fundflow=None):
    page_url = etfdb_url + ticker
    page = get_driver()
    page.goto(page_url)
    html = page.content()
    soup = bs4.BeautifulSoup(html, 'lxml')
    row_dict = {'Ticker': ticker}
    h1_list = soup.find_all('h1')
    if not h1_list:
        return None
    div_description = h1_list[0].find_next('div')
    if div_description is None or div_description.next_sibling is None:
        return None
    row_dict['Description'] = str(div_description.next_sibling).replace('\n', '')
    ul_list = soup.find_all('ul', class_='list-unstyled')
    for i in range(min(4, len(ul_list))):
        for li in ul_list[i].find_all('li'):
            span_list = li.find_all('span')
            if len(span_list) >= 2:
                row_dict[span_list[0].text] = span_list[1].text.replace('\n', '')

    if output_etfdb_fundflow:
        container = soup.find(id='fund-flow-chart-container')
        if container is not None and container.has_attr('data-series'):
            fundflow_data = container['data-series'].replace('[[', '').replace(']]', '')
            fundflow_history = []
            for fundflow_row in fundflow_data.split('], ['):
                tokens = fundflow_row.split(',')
                if len(tokens) >= 2:
                    fundflow_history.append(
                        [datetime.datetime.fromtimestamp(int(tokens[0]) / 1000).date(), tokens[1]]
                    )
            df_fundflow = pd.DataFrame(fundflow_history, columns=['Date', 'Fundflow'])
            df_fundflow.set_index('Date', inplace=True)
            df_fundflow.to_csv(output_etfdb_fundflow + ticker + '.csv')
            # dual-write (no-op unless MARKET_DATA_DB=1)
            import db
            out = df_fundflow.reset_index().rename(columns={'Fundflow': 'fundflow'})
            out['ticker'] = ticker
            db.upsert_df(out, 'raw_etfdb_fundflow', conflict_cols=['ticker', 'date'])

    return row_dict


def main():
    parser = argparse.ArgumentParser(description='scrap all etf')
    parser.add_argument('-use_firefox', action='store_true', help='Use firefox browser')
    parser.add_argument('-use_headless', action='store_true', help='Run browser headless')
    parser.add_argument('-delay', type=int, default=2, help='delay in sec between each URL request')
    parser.add_argument('-no_scrap_etf_list', action='store_true', help='no scrap etf list from etf.com and etfdb')
    parser.add_argument('-no_scrap_etfdb_info', action='store_true', help='no scrap etf info from etfdb')
    parser.add_argument('-no_scrap_etfcom_info', action='store_true', help='no scrap etf info from etf.com')
    parser.add_argument('-output_etfcom', type=str, default='data_tickers/etfs_etfcom.csv', help='etf.com etf list output file')
    parser.add_argument('-output_etfdb', type=str, default='data_tickers/etfs_etfdb.csv', help='etfdb etf list output file')
    parser.add_argument('-output_all_etfs', type=str, default='data_tickers/all_etfs.csv', help='all etfs list output file')
    parser.add_argument('-output_etfdb_info', type=str, default='data_tickers/etfdb_info.csv', help='etfdb info output file')
    parser.add_argument('-output_etfdb_fundflow', type=str, default='../stock_data/raw_etfdb_fundflow/', help='output directory for eftdb fundflow')
    parser.add_argument('-output_etfcom_info', type=str, default='data_tickers/etfcom_info.csv', help='etf.com info output file')
    parser.add_argument('-output_etfcom_holdings', type=str, default='../stock_data/raw_etfcom_holdings/', help='output directory for eft.com holdings')
    parser.add_argument('-skip', type=int, help='skip tickers')
    args = parser.parse_args()

    scrap_utils.use_firefox = args.use_firefox
    scrap_utils.use_firefox_headless = args.use_headless or True

    if not args.no_scrap_etf_list:
        page = get_driver()

        # scrape ETF list from etf.com
        df_pages = []
        page.goto('https://www.etf.com/etfanalytics/etf-finder')
        etfcom_click_understand_button()
        time.sleep(5)
        # click the "show 100 per page" control (last #inactiveResult)
        try:
            page.wait_for_selector('#inactiveResult', timeout=10000)
            page.locator('#inactiveResult').last.scroll_into_view_if_needed()
            page.locator('#inactiveResult').last.click()
            time.sleep(5)
        except Exception as exc:
            print(f'could not expand etf.com results: {exc}')

        while True:
            try:
                current = page.locator('#goToPage').first.input_value()
            except Exception:
                current = '?'
            print('scrap etf.com page', current)
            try:
                table_html = page.locator('#finderTable').first.evaluate('el => el.outerHTML')
                df_pages.append(pd.read_html(table_html, header=0, index_col=0)[0])
            except Exception as exc:
                print(f'failed to read etf.com table: {exc}')
            if page.locator('.nextPageInactive').count() > 0:
                break
            try:
                page.locator('#nextPage').first.scroll_into_view_if_needed()
                page.locator('#nextPage').first.click()
            except Exception:
                break
            time.sleep(args.delay)
        if df_pages:
            df_etfcom = pd.concat(df_pages)
            df_etfcom.to_csv(args.output_etfcom)
        else:
            df_etfcom = pd.DataFrame()

        # scrape ETF list from etfdb
        df_pages = []
        page.goto('https://etfdb.com/screener')
        while True:
            try:
                active = page.locator("li[class='active page-number']").first.inner_text()
            except Exception:
                active = '?'
            print('scrap etfdb page', active)
            try:
                thead = page.locator('thead').first.evaluate('el => el.outerHTML')
                tbody = page.locator('tbody').first.evaluate('el => el.outerHTML')
                table = '<table>' + thead + tbody + '</table>'
                df_pages.append(pd.read_html(table, header=0, index_col=0)[0])
            except Exception as exc:
                print(f'failed to read etfdb table: {exc}')
                break
            try:
                classes = page.locator('.page-next').first.get_attribute('class') or ''
                if 'disabled' in classes.split():
                    break
                page.locator('.page-next a').first.click()
            except Exception:
                break
            time.sleep(args.delay)
        if df_pages:
            df_etfdb = pd.concat(df_pages)
            for dfp in df_pages:
                dfp.drop(columns=['ETFdb Pro'], inplace=True, errors='ignore')
            df_etfdb.to_csv(args.output_etfdb)
        else:
            df_etfdb = pd.DataFrame()

        etfcom_list = set(df_etfcom.index.to_list()) if not df_etfcom.empty else set()
        etfdb_list = set(df_etfdb.index.to_list()) if not df_etfdb.empty else set()
        all_etf_list = etfcom_list | etfdb_list
        df_all = pd.DataFrame(index=sorted(all_etf_list))
        df_all.index.name = 'Ticker'
        df_all['etfcom'] = df_all.index.isin(etfcom_list)
        df_all['etfdb'] = df_all.index.isin(etfdb_list)
        df_all.to_csv(args.output_all_etfs)
    else:
        df_all = pd.read_csv(args.output_all_etfs)
        df_all.set_index('Ticker', inplace=True)

    # Scrap etfdb info
    if not args.no_scrap_etfdb_info:
        etfdb_row_dict_list = []
        for count, ticker in enumerate(df_all.index):
            if args.skip is not None and count < args.skip:
                continue
            if df_all.loc[ticker, 'etfdb']:
                print('get_etfdb_info', count, ticker)
                try:
                    row_dict = get_etfdb_info(ticker, args.output_etfdb_fundflow)
                except Exception as exc:
                    print(f'scrap fail ({exc}) - try again')
                    time.sleep(30)
                    row_dict = get_etfdb_info(ticker, args.output_etfdb_fundflow)
                if row_dict is not None:
                    etfdb_row_dict_list.append(row_dict)
                    row_dict_to_csv(etfdb_row_dict_list, args.output_etfdb_info)
                    # dual-write ref table (no-op unless MARKET_DATA_DB=1)
                    import json as _json
                    import db
                    rec = dict(row_dict)
                    desc = rec.pop('Description', None)
                    db.upsert_df(
                        pd.DataFrame([{'ticker': ticker, 'description': desc,
                                       'info': _json.dumps(rec, default=str)}]),
                        'ref_etfdb_info', conflict_cols=['ticker'],
                    )
                time.sleep(args.delay)

    # Scrap etfcom info
    if not args.no_scrap_etfcom_info:
        etfcom_row_dict_list = []
        for count, ticker in enumerate(df_all.index):
            if args.skip is not None and count < args.skip:
                continue
            if df_all.loc[ticker, 'etfcom']:
                print('get_etfcom_info', count, ticker)
                try:
                    row_dict = get_etfcom_info(ticker, args.output_etfcom_holdings)
                except Exception as exc:
                    print(f'scrap fail ({exc}) - try again')
                    time.sleep(30)
                    row_dict = get_etfcom_info(ticker, args.output_etfcom_holdings)
                if row_dict is not None:
                    etfcom_row_dict_list.append(row_dict)
                    row_dict_to_csv(etfcom_row_dict_list, args.output_etfcom_info)
                    # dual-write ref table (no-op unless MARKET_DATA_DB=1)
                    import json as _json
                    import db
                    rec = dict(row_dict)
                    desc = rec.pop('Description', None)
                    db.upsert_df(
                        pd.DataFrame([{'ticker': ticker, 'description': desc,
                                       'info': _json.dumps(rec, default=str)}]),
                        'ref_etfcom_info', conflict_cols=['ticker'],
                    )
                time.sleep(args.delay)

    close_driver()


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
