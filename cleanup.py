#!/usr/bin/env python
"""Ad-hoc cleanup snippet for CPC data.

Pass the sheet/index name as the first CLI argument, e.g.:
    uv run python cleanup.py total
"""
import sys

import pandas as pd

# clean up CPC
sheet = sys.argv[1] if len(sys.argv) > 1 else ''
df1 = pd.read_csv(f"../stock_data/temp/{sheet}.csv", header=None, index_col=0, parse_dates=True)
df2 = pd.read_csv(f"../stock_data/data_cpc/{sheet}.csv", index_col=0, parse_dates=True)
df1.columns = ['PCRatio', 'VolumeCall', 'VolumePut', 'VolumeTotal',
               'OpenInterestCall', 'OpenInterestPut', 'OpenInterestTotal']
df3 = pd.concat([df2, df1]).sort_index()
df4 = df3[df1.columns]
df4[['OpenInterestCall', 'OpenInterestPut', 'OpenInterestTotal']] = \
    df4[['OpenInterestCall', 'OpenInterestPut', 'OpenInterestTotal']].fillna(0)
df4[['OpenInterestCall', 'OpenInterestPut', 'OpenInterestTotal']] = \
    df4[['OpenInterestCall', 'OpenInterestPut', 'OpenInterestTotal']].astype(int)
df4.to_csv(f"../stock_data/data_cpc/{sheet}.csv")

# Extract ETF fund flow
# cat ../../stock_scraper/data_tickers/all_etfs.csv | xargs -n 1 -I {} -t sh -c 'grep ^{}, * > ../temp/{}.csv'

# Extract ETF fund flow
# cat ../../stock_scraper/data_tickers/all_etfs.csv | xargs -n 1 -I {} -t sh -c 'grep ^{}, * > ../temp/{}.csv'

