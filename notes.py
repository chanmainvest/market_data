#!/usr/bin/env python
"""Notes / scratch snippet: launch a headless Firefox via Playwright.

(Replaces the old Selenium snippet. PhantomJS is discontinued.)
"""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.firefox.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(5000)
    page.goto('https://example.com')
    print(page.title())
    context.close()
    browser.close()
