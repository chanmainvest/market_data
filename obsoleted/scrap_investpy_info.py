#!/usr/bin/env python

import pandas as pd
import argparse
import datetime
import time
import sys
import investpy
import glob
import os

scrap_delay = 5

def main():
    parser = argparse.ArgumentParser(description='scrap yahoo earning')
    parser.add_argument('-output_prefix', type=str, default='data_tickers/investing_', help='output file prefix')
    args = parser.parse_args()

    # Index
    indices = investpy.get_indices()
    df_index = pd.DataFrame(indices)
    df_index.to_csv(args.output_prefix + 'index_info.csv')

    # Commodity
    commodities = investpy.get_commodities()
    commodities_dict = investpy.get_commodities_dict()
    commodity_info_list = []
    for commodity,country in zip(commodities['name'].to_list(),commodities['country'].to_list()):
        print(commodity,',',country)
        commodity_info_list.append(investpy.get_commodity_information(commodity,country))
        time.sleep(scrap_delay)

    df_commodity = pd.concat(commodity_info_list)
    df_commodity.to_csv(args.output_prefix + 'commodity_info.csv')

    # ETF
    etfs_dict_us = investpy.get_etfs_dict('united states')
    etfs_dict_canada = investpy.get_etfs_dict('canada')
    df_etfs = pd.DataFrame(etfs_dict_us + etfs_dict_canada)
    df_etfs.to_csv(args.output_prefix + 'etfs_info.csv')

    # Stock
    stocks_dict_us = investpy.get_stocks_dict('united states')
    stocks_dict_canada = investpy.get_stocks_dict('canada')
    df_stocks = pd.DataFrame(stocks_dict_us + stocks_dict_canada)
    df_stocks.to_csv(args.output_prefix + 'stock_info.csv')


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
