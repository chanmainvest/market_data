#!/usr/bin/env python

import argparse
import datetime
import os
import sys

import requests

scrap_delay = 2


def main():
    parser = argparse.ArgumentParser(description='scrap finra short volume')
    parser.add_argument('-output_dir', type=str, default='../stock_data/raw_daily_short_finra/', help='output directory')
    parser.add_argument('-date', type=str, default=datetime.date.today().strftime('%Y%m%d'), help='Specify the date (YYYYMMDD)')
    args = parser.parse_args()

    url = 'https://regsho.finra.org/CNMSshvol' + args.date + '.txt'
    print('downloading', url)
    os.makedirs(args.output_dir, exist_ok=True)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    out_path = os.path.join(args.output_dir, 'CNMSshvol' + args.date + '.txt')
    with open(out_path, 'wb') as f:
        f.write(response.content)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import io
    import db
    import pandas as pd
    try:
        df_short = pd.read_csv(io.StringIO(response.text), sep='|')
        # FINRA RegSHO file ends with a summary row + blank; drop it.
        df_short = df_short[df_short['Date'].astype(str).str.fullmatch(r'\d{8}')]
        df_short.rename(columns={
            'Date': 'date_raw', 'Symbol': 'symbol',
            'ShortVolume': 'short_volume', 'ShortExemptVolume': 'short_exempt_volume',
            'TotalVolume': 'total_volume', 'Market': 'market',
        }, inplace=True)
        df_short['date'] = pd.to_datetime(df_short['date_raw'], format='%Y%m%d').dt.date
        db.upsert_df(df_short, 'raw_short_finra', conflict_cols=['symbol', 'date', 'market'])
    except Exception as exc:
        print(f'db write skipped: {exc}')


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
