#!/usr/bin/env python
"""Scrape bond yield data from FINRA/Morningstar Bond Center.

Rewritten to use Playwright (the legacy Selenium/PhantomJS stack is
discontinued). The flow is otherwise faithful to the original.
"""

import argparse
import datetime
import sys
import time

import bs4
import pandas as pd

import scrap_utils
from scrap_utils import *  # noqa: F401,F403  (legacy star-import contract)

# -----------------------------------------------------------------
# hand crafted scrapper
# -----------------------------------------------------------------
result_url = 'https://finra-markets.morningstar.com/BondCenter/Results.jsp'
bond_search_url = 'https://finra-markets.morningstar.com/bondSearch.jsp'
scrap_delay = 10


def main():
    parser = argparse.ArgumentParser(description='scrap bond yield from finra')
    parser.add_argument('-use_firefox', action='store_true', help='Use firefox browser')
    parser.add_argument('-use_headless', action='store_true', help='Run browser headless')
    parser.add_argument('-output_prefix', type=str, default='../stock_data/raw_bonds_finra/bonds_', help='prefix of the output file')
    parser.add_argument('-today', action='store_true', help='Trade Date = today')
    parser.add_argument('-price', type=int, default=70, help='zero to the price range ')
    args = parser.parse_args()

    # initialize browser (single instance — old code spawned a second one)
    scrap_utils.use_firefox = args.use_firefox
    scrap_utils.use_firefox_headless = args.use_headless or True
    page = get_driver()

    # bypass agreement page
    page.goto(result_url)
    try:
        page.locator('.agree').first.click(timeout=5000)
    except Exception:
        pass

    # enter search filter
    try:
        page.get_by_text('EDIT SEARCH', exact=False).first.click(timeout=5000)
    except Exception:
        pass
    try:
        page.locator('.hide').first.click(timeout=5000)
    except Exception:
        pass

    # subProductType = Corporate
    try:
        page.locator('select[name="subProductType"]').select_option('1')
    except Exception as exc:
        print(f'could not set subProductType: {exc}')

    trade_params = page.locator('#firscreener-tradeParameters')

    if args.today:
        date_inputs = trade_params.locator('input[name="tradeDate"]')
        date_inputs.nth(0).click()
        page.locator('.today').first.click()
        date_inputs.nth(1).click()
        page.locator('.today').first.click()

    price_inputs = trade_params.locator('input[name="tradePrice"]')
    price_inputs.nth(0).fill('0')
    price_inputs.nth(1).fill(str(args.price))

    try:
        page.locator("input[value='SHOW RESULTS']").first.click()
    except Exception as exc:
        print(f'could not click SHOW RESULTS: {exc}')

    time.sleep(1)
    total_el = page.locator('.qs-pageutil-total')
    try:
        total_text = total_el.first.inner_text(timeout=5000)
        total_page = int(total_text.split()[1])
    except Exception:
        total_page = 1
    print('total pages:', total_page)

    # scrape the data table
    columns = []
    row_data = []

    for i in range(total_page):
        page_num = page.locator('.qs-pageutil-input').first.input_value()
        print('page', page_num)

        page_source = page.content()
        soup = bs4.BeautifulSoup(page_source, 'lxml')
        resultdata = soup.find('div', class_='qs-resultData-body')

        if resultdata is None:
            print('no result data found on page, stopping')
            break

        # column headers
        if page_num == '1':
            gridhd = resultdata.find('div', class_='rtq-grid-hd')
            if gridhd is not None:
                columns = [cell.text for cell in gridhd.find_all('div', class_='rtq-grid-cell-ctn')[1:]]

        gridbd = resultdata.find('div', class_='rtq-grid-bd')
        if gridbd is not None:
            for row in gridbd.find_all('div', class_='rtq-grid-row'):
                row_data.append([cell.text for cell in row.find_all('div', class_='rtq-grid-cell-ctn')[1:]])

        # Next link — bs4 renamed `text=` to `string=`
        next_link = soup.find('a', string='Next')
        if next_link is None or 'qs-pageutil-disable' in (next_link.get('class') or []):
            break
        try:
            page.get_by_text('Next', exact=True).first.click()
        except Exception:
            break
        time.sleep(scrap_delay)

    df = pd.DataFrame(row_data, columns=columns or None)
    csv_filename = args.output_prefix + str(datetime.date.today()) + '.csv'
    df.to_csv(csv_filename)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    # FINRA bonds key on CUSIP; if absent, fall back to the bond symbol.
    id_col = 'Cusip' if 'Cusip' in df.columns else (columns[0] if columns else 'bond_id')
    rows = []
    for _, r in df.iterrows():
        rec = {'date': str(datetime.date.today()), 'cusip': str(r.get(id_col, ''))}
        for c in df.columns:
            rec[c] = r[c]
        rows.append(rec)
    db.upsert_jsonb_rows('raw_bonds_finra', ['date', 'cusip'], list(df.columns), rows)

    close_driver()


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
