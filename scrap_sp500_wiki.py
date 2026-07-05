#!/usr/bin/env python
"""Get the S&P 500 constituent list (current + historical) from Wikipedia.

Run:  uv run python scrap_sp500_wiki.py [output.csv]
"""
import sys

import numpy as np
import pandas as pd

# Get S&P500 list from Wiki
data = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
cur_symbols = data[0]['Symbol']
added_symbols = data[1][('Added', 'Ticker')]
removed_symbols = data[1][('Removed', 'Ticker')]
symbols = set()
symbols.update(cur_symbols.to_list())
symbols.update(added_symbols.to_list())
symbols.update(removed_symbols.to_list())
symbols.discard(np.nan)

df = pd.DataFrame(sorted(symbols), columns=['Ticker'])
out = sys.argv[1] if len(sys.argv) > 1 else 'data_tickers/sp500_wiki.csv'
df.to_csv(out, index=False)
print(f'wrote {len(df)} symbols to {out}')

# dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
import db
db.upsert_df(df.rename(columns={'Ticker': 'ticker'}), 'ref_sp500_wiki', conflict_cols=['ticker'])
