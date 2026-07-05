#!/usr/bin/env python

import pandas as pd
import argparse
import datetime
import sys
from junit_xml import TestSuite, TestCase
from scrap_utils import *

def main():
    parser = argparse.ArgumentParser(description='generate report from finviz daily data')
    parser.add_argument('-input', type=str, help='input file')
    parser.add_argument('-output', type=str, default='daily_report.xml', help='output file')
    args = parser.parse_args()

    if args.input is None:
        filename = '../stock_data/raw_daily_finviz/finviz_' + str(datetime.date.today()) + '.csv'
    else:
        filename = args.input

    # generate report
    df = pd.read_csv(filename)
    df.set_index('Ticker', inplace=True)
    df.drop_duplicates(inplace=True)
    # Ensure string-typed columns for the .find() string checks below.
    df['Market Cap'] = df['Market Cap'].astype(str)
    df['Change'] = df['Change'].astype(str)
    ts_list = []
    for sector in df.Sector.unique():
        ts = TestSuite(name=sector)
        df_sector = df[df['Sector'] == sector]
        for industry in df_sector.Industry.unique():
            for ticker in df.index[df['Industry'] == industry]:
                market_cap = df.loc[ticker, 'Market Cap']
                if 'B' in market_cap:
                    print(sector, '-', industry, '-', ticker, '-', df.loc[ticker, 'Change'])
                    tc = TestCase(classname=industry,
                                  name=ticker,
                                  elapsed_sec=df.loc[ticker, 'Price'],
                                  stdout=df.loc[ticker, 'Change'],
                                  stderr=market_cap)
                    if '-' in df.loc[ticker, 'Change']:
                        tc.add_error_info(message='lower')
                    ts.test_cases.append(tc)
        ts_list.append(ts)

    with open(args.output, 'w') as f:
        TestSuite.to_file(f, ts_list, prettyprint=True)

if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)

