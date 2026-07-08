#!/usr/bin/env python
"""Shared scraping utilities.

HTTP helpers use ``requests`` (optionally ``cloudscraper`` to bypass
Cloudflare). Browser automation uses **Playwright** (replacing the legacy
Selenium/PhantomJS stack, both of which are discontinued).

Yahoo Finance calls can be distributed across multiple egress IPs via a
round-robin SOCKS5 proxy pool (``ProxyPool``) built on ``ssh -D`` tunnels,
mirroring the knowledge_base YouTube scraper. This avoids Yahoo's per-IP
rate limiting (HTTP 429) without a paid rotating-proxy service.
"""

import datetime
import os
import socket
import subprocess
import sys
import time

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
_proxy_pool = None              # cached ProxyPool (set via init_proxy_pool)


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
    'ProxyPool',
    'init_proxy_pool',
    'next_proxy',
    'next_proxy_session',
    'stop_proxy_pool',
]


# ---------------------------------------------------------------------------
# Proxy pool — round-robin SOCKS5 over SSH tunnels (ssh -D)
# Mirrors knowledge_base/src/kb/scrapers/proxy.py. Distributes Yahoo Finance
# requests across multiple egress IPs to avoid per-IP rate limiting (429).
# ---------------------------------------------------------------------------

# Local ports are assigned consecutively from this base. 1081+ avoids the
# common 1080 default so a manually-opened tunnel there isn't clobbered.
_BASE_PORT = 1081
# Seconds to wait for each tunnel's SOCKS port to accept connections.
_READY_TIMEOUT = 12.0


class ProxyPool:
    """A round-robin pool of SSH dynamic-forward (SOCKS5) tunnels.

    Each ``ssh -D <port> -N <host>`` subprocess exposes a local
    ``socks5://127.0.0.1:<port>`` endpoint whose egress IP is the SSH host's.
    Used as a context manager so tunnels are torn down when the scrape ends::

        with ProxyPool(["oc1.hevangel.com", "serv00"]) as pool:
            scraper.run(...)           # calls next_proxy() per request

    The SSH hosts must be resolvable aliases in ``~/.ssh/config`` with key
    auth (no password prompt).
    """

    def __init__(self, hosts: list[str], base_port: int = _BASE_PORT) -> None:
        self.hosts = list(hosts)
        self.base_port = base_port
        self._procs: list[tuple[str, int, subprocess.Popen]] = []
        self._urls: list[str] = []
        self._idx = 0

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "ProxyPool":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> list[str]:
        """Spawn one ``ssh -D`` tunnel per host. Returns the live
        ``socks5h://127.0.0.1:<port>`` URLs (dead tunnels are skipped).

        Uses ``socks5h://`` (not ``socks5://``) so DNS resolution happens
        at the tunnel's egress, not locally — required for requests/urllib
        to route HTTPS through the proxy correctly.

        Each tunnel binds a *free* local port rather than ``base_port+i`` so
        orphaned ssh processes from a previous run can't cause a silent
        ``ExitOnForwardFailure`` collision."""
        for i, host in enumerate(self.hosts):
            port = self._next_free_port(self.base_port + i)
            url = f"socks5h://127.0.0.1:{port}"
            try:
                proc = subprocess.Popen(
                    ["ssh", "-D", str(port), "-N",
                     "-o", "ExitOnForwardFailure=yes",
                     "-o", "ServerAliveInterval=15",
                     "-o", "ServerAliveCountMax=2",
                     "-o", "TCPKeepAlive=yes",
                     "-o", "ConnectTimeout=10",
                     host],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    **self._popen_kwargs(),
                )
            except FileNotFoundError:
                print('ssh not found on PATH; cannot open proxy tunnels')
                break
            if self._wait_ready(port):
                self._procs.append((host, port, proc))
                self._urls.append(url)
                print(f'proxy tunnel up: {host} -> {url} (pid {proc.pid})')
            else:
                self._kill_proc(proc)
                print(f'proxy tunnel FAILED for {host} on port {port} (skipped)')
        if not self._urls:
            print('no proxy tunnels came up; requests will go direct')
        return list(self._urls)

    def stop(self) -> None:
        """Terminate every tunnel ssh process. Uses a forceful kill on Windows
        where ``terminate()`` on ssh.exe is unreliable."""
        for host, port, proc in self._procs:
            if proc.poll() is None:
                self._kill_proc(proc)
                print(f'proxy tunnel down: {host} -> 127.0.0.1:{port}')
        self._procs.clear()
        self._urls.clear()
        self._idx = 0

    # -- round-robin --------------------------------------------------------
    def next(self) -> str | None:
        """Return the next live proxy URL in round-robin order, or None if
        no tunnel is alive (caller connects direct)."""
        self._reap()
        if not self._urls:
            return None
        url = self._urls[self._idx % len(self._urls)]
        self._idx += 1
        return url

    def _reap(self) -> None:
        """Drop any tunnel whose ssh process has exited."""
        if not self._procs:
            return
        alive: list[tuple[str, int, subprocess.Popen]] = []
        dead: list[tuple[str, int, subprocess.Popen]] = []
        for entry in self._procs:
            (dead if entry[2].poll() is not None else alive).append(entry)
        if not dead:
            return
        for host, port, _ in dead:
            print(f'proxy tunnel reaped (ssh exited): {host} -> 127.0.0.1:{port}')
        self._procs = alive
        self._urls = [f"socks5h://127.0.0.1:{port}" for _, port, _ in alive]
        if self._urls:
            self._idx %= len(self._urls)

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _wait_ready(port: int, timeout: float = _READY_TIMEOUT) -> bool:
        """Poll until the local SOCKS port accepts a connection."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.3)
        return False

    @staticmethod
    def _next_free_port(preferred: int) -> int:
        """Return the first free localhost TCP port at or above *preferred*."""
        for port in range(preferred, preferred + 64):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @staticmethod
    def _popen_kwargs() -> dict:
        """Platform-specific kwargs to keep the tunnel cleanly attached."""
        if sys.platform == "win32":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    @staticmethod
    def _kill_proc(proc: subprocess.Popen) -> None:
        """Forcefully terminate an ssh tunnel on every platform."""
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def init_proxy_pool(hosts: list[str] | None = None) -> ProxyPool | None:
    """Build and start a ProxyPool from a host list or the ``YAHOO_PROXY_HOSTS``
    env var (comma-separated SSH aliases). Starts the tunnels and caches the
    pool module-globally so ``next_proxy()`` can cycle through them.

    Returns the pool (or None if no hosts configured). The caller is
    responsible for calling ``stop_proxy_pool()`` at the end of the scrape.
    """
    global _proxy_pool
    if hosts is None:
        spec = os.environ.get('YAHOO_PROXY_HOSTS', '')
        hosts = [h.strip() for h in spec.split(',') if h.strip()]
    if not hosts:
        return None
    if _proxy_pool is not None:
        _proxy_pool.stop()
    _proxy_pool = ProxyPool(hosts)
    _proxy_pool.start()
    if _proxy_pool.urls:
        print(f'proxy round-robin across {len(_proxy_pool.urls)} tunnel(s): '
              + ', '.join(_proxy_pool.urls))
    else:
        _proxy_pool = None
    return _proxy_pool


def next_proxy() -> str | None:
    """Return the next SOCKS5 proxy URL from the module-global pool, or None
    if no pool is active. Yahoo scrapers call this per-request and pass the
    result to yfinance/yahooquery's ``proxy=`` kwarg."""
    if _proxy_pool is None:
        return None
    return _proxy_pool.next()


def next_proxy_session():
    """Return a ``requests.Session`` routed through the next proxy, or None
    if no pool is active. Modern yfinance (1.5+) takes ``session=`` rather
    than ``proxy=``; yahooquery accepts ``proxy=`` directly."""
    import requests as _requests
    url = next_proxy()
    if not url:
        return None
    s = _requests.Session()
    s.proxies.update({"http": url, "https": url})
    return s


def stop_proxy_pool() -> None:
    """Tear down the module-global proxy pool if one is active."""
    global _proxy_pool
    if _proxy_pool is not None:
        _proxy_pool.stop()
        _proxy_pool = None


def parse_proxy_hosts(spec: str) -> list[str]:
    """Parse a comma-separated host spec into a clean list of hostnames."""
    return [h.strip() for h in spec.split(',') if h.strip()]


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
