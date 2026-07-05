#!/usr/bin/env python
"""Shared scraping utilities.

HTTP helpers use ``requests`` (optionally ``cloudscraper`` to bypass
Cloudflare). Browser automation uses **Playwright** (replacing the legacy
Selenium/PhantomJS stack, both of which are discontinued).
"""

import datetime

import bs4
import cloudscraper
import pandas as pd
import requests
from pandas.tseries.offsets import BDay
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Module-level configuration toggles. Set these before calling the helpers.
# ---------------------------------------------------------------------------
use_cloudscrapper = False       # use cloudscraper instead of plain requests
use_firefox = False             # use Firefox instead of Chromium
use_firefox_headless = True     # run the browser headless (default True)

_scrapper = None                # cached cloudscraper/requests session
_browser_ctx = None             # cached (playwright, browser, page) tuple


__all__ = [
    'use_cloudscrapper',
    'use_firefox',
    'use_firefox_headless',
    'get_scrapper',
    'get_driver',
    'close_driver',
    'click_link',
    'click_class_name',
    'click_xpath',
    'get_session',
    'get_url',
    'post_url',
    'get_df_from_page',
    'is_market_close',
    'get_prev_market_date',
    'row_dict_to_csv',
    'df_to_csv',
    'onDay',
]


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
def get_scrapper():
    """Return a ``requests``-compatible session (plain or cloudscraper)."""
    global _scrapper
    if not use_cloudscrapper:
        return requests
    if _scrapper is None:
        _scrapper = cloudscraper.create_scraper(browser='firefox')
    return _scrapper


def get_url(url):
    """HTTP GET returning the response body as text, or None on failure."""
    response = get_scrapper().get(url, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code != requests.codes.ok:
        print('Error', response.url, '- response code:', response.status_code)
        return None
    return response.text


def post_url(url, data):
    """HTTP POST returning the response body as text, or None on failure."""
    response = get_scrapper().post(url, data=data, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code != requests.codes.ok:
        print('Error', response.url, '- response code:', response.status_code)
        return None
    return response.text


# ---------------------------------------------------------------------------
# Browser layer (Playwright)
# ---------------------------------------------------------------------------
def get_driver(implicitly_wait=10):
    """Return a cached Playwright page.

    ``implicitly_wait`` is honoured via ``page.set_default_timeout``.
    The previous Selenium/PhantomJS implementation is gone — PhantomJS was
    removed in Selenium 4 and ``find_element_by_*`` was removed in 4.3+.

    Returns the active ``playwright.sync_api.Page``.
    """
    global _browser_ctx
    if _browser_ctx is None:
        pw = sync_playwright().start()
        browser_type = pw.firefox if use_firefox else pw.chromium
        browser = browser_type.launch(headless=use_firefox_headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(implicitly_wait * 1000)
        _browser_ctx = (pw, browser, context, page)
    return _browser_ctx[3]


def close_driver():
    """Shut down the cached browser/playwright instance, if any."""
    global _browser_ctx
    if _browser_ctx is not None:
        pw, browser, context, page = _browser_ctx
        try:
            context.close()
            browser.close()
            pw.stop()
        except Exception:
            pass
        _browser_ctx = None


# --- thin Selenium-style helpers (kept for compatibility with old callers) ---
def click_link(link_text):
    """Click the first link whose visible text matches ``link_text``."""
    page = get_driver()
    try:
        page.get_by_text(link_text, exact=False).first.click()
    except Exception:
        pass


def click_class_name(class_name):
    """Click the first element matching the given CSS class."""
    page = get_driver()
    try:
        page.locator(f'.{class_name}').first.click()
    except Exception:
        pass


def click_xpath(xpath):
    """Click the first element matching the given XPath."""
    page = get_driver()
    try:
        page.locator(f'xpath={xpath}').first.click()
    except Exception:
        pass


def get_session():
    """Build a ``requests.Session`` seeded with the browser's cookies."""
    session = requests.Session()
    page = get_driver()
    context = _browser_ctx[2]
    for cookie in context.cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    return session


# ---------------------------------------------------------------------------
# HTML / DataFrame helpers
# ---------------------------------------------------------------------------
def get_df_from_page(page, table_index=0, header=0, index_col=0, drop_columns=None):
    """Parse an HTML table from ``page`` (str) into a DataFrame."""
    soup = bs4.BeautifulSoup(page, 'lxml')
    table_list = soup.find_all('table')
    if not table_list:
        return None
    table = table_list[table_index]
    df = pd.concat(pd.read_html(str(table), header=header, index_col=index_col))
    if drop_columns is not None:
        df.drop(columns=drop_columns, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Market calendar helpers
# ---------------------------------------------------------------------------
def is_market_close(date):
    """True if ``date`` (str YYYY-MM-DD) is in market_close_dates.txt."""
    with open('market_close_dates.txt', 'r') as reader:
        market_close_dates = reader.read().splitlines()
    return date in market_close_dates


def get_prev_market_date(date):
    """Return the previous trading day, skipping close dates."""
    prev_date = (date.today() - BDay(1)).date()
    if is_market_close(str(prev_date)):
        prev_date = (prev_date - BDay(1)).date()
    return prev_date


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------
def row_dict_to_csv(row_dict_list, csv, index_column='Ticker'):
    df = pd.DataFrame(row_dict_list)
    df.set_index(index_column, inplace=True)
    df.to_csv(csv)


def df_to_csv(df, output_prefix, start_date, end_date=None):
    if start_date == end_date or end_date is None:
        df.insert(0, 'Date', start_date, True)
        filename = output_prefix + start_date + '.csv'
    else:
        df.insert(0, 'Start Date', start_date, True)
        df.insert(0, 'End Date', end_date, True)
        filename = output_prefix + start_date + '_' + end_date + '.csv'
    df.to_csv(filename)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def onDay(date, day):
    """Return the next weekday ``day`` (Mon=0..Sun=6) on or after ``date``."""
    return date + datetime.timedelta(days=(day - date.weekday() + 7) % 7)
