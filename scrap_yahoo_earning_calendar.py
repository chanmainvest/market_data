#!/usr/bin/env python

import argparse
import datetime
import sys
import time

import pandas as pd
import yfinance as yf

scrap_delay = 2


def onDay(date, day):
    """
    :param date: current date
    :param day: next monday(0) - sunday(6)
    :return:
    """
    return date + datetime.timedelta(days=(day - date.weekday() + 7) % 7)


def _extract_earnings_date(cal):
    """Modern yfinance returns ``Ticker.calendar`` as a dict (single next
    earnings), a DataFrame (weekly view), or None. Return a single
    ``datetime`` for the next earnings date, or None."""
    if cal is None:
        return None
    # Dict form: {'Earnings Date': [<date>, ...], 'Earnings Average': ...}
    if isinstance(cal, dict):
        raw = cal.get('Earnings Date')
        if raw is None:
            return None
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if isinstance(raw, (datetime.datetime, datetime.date)):
            return raw if isinstance(raw, datetime.date) else raw.date()
        if isinstance(raw, pd.Timestamp):
            return raw.date()
        if isinstance(raw, str):
            try:
                return pd.to_datetime(raw).date()
            except Exception:
                return None
        return None
    # DataFrame form (older / weekly view)
    try:
        if cal.shape[1] == 0:
            return None
        if cal.shape[1] > 1:
            val = cal.at['Earnings Date', 0]
        else:
            val = cal.at['Earnings Date', 'Value']
        if hasattr(val, 'date'):
            return val.date()
        return pd.to_datetime(val).date()
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='scrap yahoo earning')
    parser.add_argument('-input', type=str, default='data_tickers/earnings.csv', help='input file')
    parser.add_argument('-output_prefix', type=str, default='data_yahoo_earnings_estimate/earnings_estimate_', help='output file')
    parser.add_argument('-today', type=str, help='Specify today date')
    args = parser.parse_args()

    if args.today is None:
        today = datetime.date.today()
    else:
        today = datetime.datetime.fromisoformat(args.today).date()
    next_monday = onDay(today, 0)
    next_friday = onDay(next_monday, 4)
    df_input = pd.read_csv(args.input, comment='#')
    df_input.set_index('Ticker', inplace=True)
    df_output = pd.DataFrame()

    for ticker in df_input.index:
        print(ticker)
        yf_ticker = yf.Ticker(ticker)
        try:
            yf_calendar = yf_ticker.calendar
        except Exception:
            print(f"{ticker} has no earnings date yet")
            time.sleep(scrap_delay)
            continue

        next_earnings_date = _extract_earnings_date(yf_calendar)
        if next_earnings_date is None:
            time.sleep(scrap_delay)
            continue

        print(f"{ticker} next earnings at {next_earnings_date}")
        if next_monday <= next_earnings_date <= next_friday:
            # Build a single-row frame from the dict (or DataFrame transpose).
            if isinstance(yf_calendar, dict):
                new_row = pd.DataFrame([yf_calendar])
            else:
                new_row = yf_calendar.T
            new_row.insert(1, 'Ticker', ticker)
            report = df_input.at[ticker, 'Report']
            new_row.insert(2, 'Report', report)
            # pandas 2.0 removed DataFrame.append; use concat.
            df_output = pd.concat([df_output, new_row], ignore_index=True)

        time.sleep(scrap_delay)

    df_output.reset_index(drop=True, inplace=True)
    if 'Earnings Date' in df_output.columns:
        df_output.sort_values(by=['Earnings Date', 'Ticker'], inplace=True)
    print(df_output)
    df_output.to_csv(args.output_prefix + str(onDay(today, 0)) + '.csv', index=False)

    # dual-write into Postgres (no-op unless MARKET_DATA_DB=1)
    import db
    if not df_output.empty:
        out = df_output.copy()
        out['earnings_week_monday'] = str(onDay(today, 0))
        db.upsert_df(out, 'raw_yahoo_earnings', conflict_cols=['earnings_week_monday', 'ticker'])


if __name__ == "__main__":
    status = main()
    sys.exit(0 if status is None else status)
