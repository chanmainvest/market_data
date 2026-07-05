"""Reconcile price history across raw data sources.

Reads the per-source raw hypertables (Yahoo, Alpha Vantage, Macrotrends),
normalizes each source's column convention (Yahoo stores adjusted prices as
canonical; Alpha Vantage stores raw; Macrotrends stores adjusted), then
takes a per-row mode across sources — falling back to the median when no
majority — exactly like the legacy cleanup_etf_history.py. Writes the
consensus row into reconcile_price_history with a source_count and sources[]
so the UI can flag disagreement.

Run:  mdata reconcile [--ticker AAPL] [--batch-size 200]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from .db import engine, session


def _read_tickers_to_reconcile(batch_size: int | None) -> list[str]:
    """Union of tickers present in any of the three history sources."""
    with engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ticker FROM raw_yahoo_history
                UNION SELECT DISTINCT ticker FROM raw_alpha_vantage_history
                UNION SELECT DISTINCT ticker FROM raw_macrotrends_history
                ORDER BY ticker
                LIMIT COALESCE(:n, 100000000)
                """
            ),
            {"n": batch_size},
        ).fetchall()
    return [r[0] for r in rows]


def _load_source(ticker: str, table: str) -> pd.DataFrame | None:
    with engine().connect() as conn:
        df = pd.read_sql(
            text(f"SELECT * FROM {table} WHERE ticker = :t ORDER BY date"),
            conn,
            params={"t": ticker},
            parse_dates=["date"],
        )
    if df.empty:
        return None
    df = df.set_index("date")
    return df


def _normalize_yahoo(df: pd.DataFrame) -> pd.DataFrame:
    """Yahoo: stores Open/High/Low/Close (raw) + adj_close. Derive adj OHLC
    from the close ratio, mirroring cleanup_etf_history."""
    out = pd.DataFrame(index=df.index)
    out["Open"] = df.get("open")
    out["High"] = df.get("high")
    out["Low"] = df.get("low")
    out["Close"] = df.get("close")
    ratio = (df.get("adj_close") / df.get("close")).replace([np.inf, -np.inf], np.nan)
    out["AdjOpen"] = df.get("open") * ratio
    out["AdjHigh"] = df.get("high") * ratio
    out["AdjLow"] = df.get("low") * ratio
    out["AdjClose"] = df.get("adj_close")
    out["Volume"] = df.get("volume")
    out["Dividend"] = df.get("dividend").fillna(0.0)
    out["Split"] = df.get("split_ratio").fillna(1.0)
    return out


def _normalize_alpha_vantage(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["Open"] = df.get("open")
    out["High"] = df.get("high")
    out["Low"] = df.get("low")
    out["Close"] = df.get("close")
    out["AdjOpen"] = df.get("open")
    out["AdjHigh"] = df.get("high")
    out["AdjLow"] = df.get("low")
    out["AdjClose"] = df.get("adjusted_close")
    out["Volume"] = df.get("volume")
    out["Dividend"] = df.get("dividend_amount").fillna(0.0)
    out["Split"] = df.get("split_coefficient").fillna(1.0)
    return out


def _normalize_macrotrends(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["Open"] = df.get("adj_open")
    out["High"] = df.get("adj_high")
    out["Low"] = df.get("adj_low")
    out["Close"] = df.get("close")
    out["AdjOpen"] = df.get("adj_open")
    out["AdjHigh"] = df.get("adj_high")
    out["AdjLow"] = df.get("adj_low")
    out["AdjClose"] = df.get("adj_close")
    out["Volume"] = df.get("volume")
    out["Dividend"] = np.nan
    out["Split"] = 1.0
    return out


FIELDS = ["Open", "High", "Low", "Close", "AdjOpen", "AdjHigh", "AdjLow",
          "AdjClose", "Volume", "Dividend", "Split"]


def _consensus(df_multi: pd.DataFrame, sources: list[str]) -> pd.DataFrame:
    """Given a wide frame with MultiIndex columns (source, field), return
    the reconciled Data series. Mode with median fallback when no majority."""
    n_sources = len(sources)
    out = pd.DataFrame(index=df_multi.index)
    for field in FIELDS:
        # Build a per-date DataFrame: one column per source for this field.
        cols = {s: df_multi[(s, field)] for s in sources if (s, field) in df_multi.columns}
        if not cols:
            out[field] = np.nan
            continue
        sub = pd.DataFrame(cols, index=df_multi.index)
        sub = sub.dropna(how="all")
        if sub.empty:
            out[field] = np.nan
            continue
        rounded = sub.round(2) if field != "Split" else sub.round(4)
        mode_vals = rounded.mode(axis=1)
        if n_sources >= 3 and mode_vals.shape[1] >= 2:
            chosen = sub.median(axis=1)
        else:
            chosen = mode_vals[0]
        out[field] = chosen
    return out


def reconcile_ticker(ticker: str) -> int:
    """Reconcile one ticker; return number of rows written."""
    raw_sources = {
        "yahoo": ("raw_yahoo_history", _normalize_yahoo),
        "alpha_vantage": ("raw_alpha_vantage_history", _normalize_alpha_vantage),
        "macrotrends": ("raw_macrotrends_history", _normalize_macrotrends),
    }

    frames: dict[str, pd.DataFrame] = {}
    for name, (table, normalizer) in raw_sources.items():
        raw = _load_source(ticker, table)
        if raw is None or raw.empty:
            continue
        frames[name] = normalizer(raw)

    if not frames:
        return 0

    # Align on the union of dates, last 2 trimmed (matches legacy behavior).
    all_dates = sorted(set.union(*[set(f.index) for f in frames.values()]))[:-2]
    if not all_dates:
        return 0

    present = {n: f for n, f in frames.items()}
    # Build the wide MultiIndex frame
    df_multi = pd.concat(present, axis=1, names=["source", "field"])
    df_multi = df_multi.loc[all_dates]

    sources_present = list(present.keys())
    consensus = _consensus(df_multi, sources_present)
    # Split factor = cumulative product of split ratios (reverse time)
    consensus["SplitFactor"] = consensus["Split"][::-1].cumprod().shift(1, fill_value=1.0)

    # Build output rows
    consensus = consensus.reset_index().rename(columns={"index": "date"})
    consensus["ticker"] = ticker
    consensus["source_count"] = len(sources_present)
    consensus["sources"] = [sources_present] * len(consensus)

    # Rename to snake_case for the DB
    rename_map = {
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "AdjOpen": "adj_open", "AdjHigh": "adj_high", "AdjLow": "adj_low",
        "AdjClose": "adj_close", "Volume": "volume", "Dividend": "dividend",
        "Split": "split_ratio", "SplitFactor": "split_factor",
    }
    consensus = consensus.rename(columns=rename_map)

    # Ensure 'date' column exists (reset_index may have named it 'date' or
    # the original index name like 'index').
    if consensus.columns[0] not in ("date", "ticker"):
        consensus = consensus.rename(columns={consensus.columns[0]: "date"})

    n = _upsert_reconciled(consensus)
    return n


def _upsert_reconciled(df: pd.DataFrame) -> int:
    """Upsert a reconciled DataFrame into reconcile_price_history.

    Uses the mdata engine directly (always writes — not gated by the
    MARKET_DATA_DB env flag, unlike the scraper dual-write path).
    """
    from sqlalchemy import MetaData, Table, text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    conflict_cols = ["ticker", "date"]

    with engine().connect() as conn:
        table_cols = {
            r[0] for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='reconcile_price_history'")
            ).fetchall()
        }
    df = df[[c for c in df.columns if c in table_cols]]
    if df.empty:
        return 0

    md = MetaData()
    tbl = Table("reconcile_price_history", md, autoload_with=engine())
    records = []
    for _, row in df.iterrows():
        rec = {}
        for c in df.columns:
            v = row[c]
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, float) and pd.isna(v):
                v = None
            rec[c] = v
        # sources is a list — pass as-is; psycopg adapts Python lists to PG arrays
        if "sources" in rec and not isinstance(rec["sources"], (list, type(None))):
            rec["sources"] = list(rec["sources"]) if rec["sources"] is not None else None
        records.append(rec)

    update_cols = [c for c in df.columns if c not in conflict_cols]
    stmt = pg_insert(tbl).values(records)
    if update_cols:
        set_map = {c: getattr(stmt.excluded, c) for c in update_cols}
        stmt = stmt.on_conflict_do_update(index_elements=conflict_cols, set_=set_map)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
    with engine().begin() as conn:
        conn.execute(stmt)
    return len(records)


def main(ticker: str | None = None, batch_size: int | None = None) -> int:
    tickers = [ticker] if ticker else _read_tickers_to_reconcile(batch_size)
    if not tickers:
        print("no tickers to reconcile")
        return 0
    print(f"reconciling {len(tickers)} tickers")
    total = 0
    for i, t in enumerate(tickers, 1):
        try:
            n = reconcile_ticker(t)
            total += n
            print(f"[{i}/{len(tickers)}] {t}: {n} rows")
        except Exception as exc:
            print(f"[{i}/{len(tickers)}] {t}: FAILED ({exc})", file=sys.stderr)
    print(f"done: {total} reconciled rows")
    return 0
