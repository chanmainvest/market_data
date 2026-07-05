"""Bulk-ingest legacy scraped CSVs from the data/ submodule into Postgres.

Each loader is tailored to the exact on-disk shape of the old data (which
differs slightly from what the modern scrapers emit — e.g. raw_history_yahoo
has no Adj Close / Dividend / Split columns). All writes go through the
shared market_data/market_data/db.py upsert helpers, so re-runs are
idempotent.

Run from the project root:
    uv run python -m mdata.ingest <source>
    uv run python -m mdata.ingest all
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import pandas as pd

# Force-enable DB writes for the ingest run, then import the shared writer.
os.environ.setdefault("MARKET_DATA_DB", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "market_data"))
import db as writer  # noqa: E402

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_float(s):
    """Parse shorthand like '24.40B', '0.18%', '$436.6 M' into float."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", "").replace("$", "").replace("%", "")
    if s in ("", "-", "n/a", "N/A"):
        return None
    mult = 1.0
    if s.endswith(("B", "b")):
        mult = 1e9
        s = s[:-1]
    elif s.endswith(("M", "m")):
        mult = 1e6
        s = s[:-1]
    elif s.endswith(("K", "k")):
        mult = 1e3
        s = s[:-1]
    elif s.endswith(("T", "t")):
        mult = 1e12
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _folder(name: str) -> Path:
    p = DATA_ROOT / name
    if not p.exists():
        print(f"  skip: {p} does not exist")
        return Path()
    return p


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def ingest_yahoo_history() -> int:
    """raw_history_yahoo/<TICKER>.csv — OHLCV per ticker."""
    folder = _folder("raw_history_yahoo")
    if not folder:
        return 0
    files = sorted(folder.glob("*.csv"))

    # Skip tickers already loaded (resume-friendly; upserts are idempotent
    # but re-checking 7000 files of existing data is slow).
    from sqlalchemy import text as _text
    eng = writer.engine()
    with eng.connect() as conn:
        done = {r[0] for r in conn.execute(_text("SELECT DISTINCT ticker FROM raw_yahoo_history")).fetchall()}
    print(f"  {len(done)} tickers already loaded; skipping those", flush=True)

    total = 0
    processed = 0
    for i, f in enumerate(files, 1):
        ticker = f.stem.strip()
        if ticker in done:
            continue
        processed += 1
        try:
            df = pd.read_csv(f)
            if "Date" not in df.columns:
                continue
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
        except Exception as exc:
            print(f"  skip {ticker}: {exc}")
            continue
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
            "Dividend": "dividend", "Split": "split_ratio",
        })
        df["ticker"] = ticker
        df["date"] = df["date"].dt.date
        total += writer.upsert_df(df, "raw_yahoo_history", ["ticker", "date"])
        if processed % 500 == 0:
            print(f"  [{processed} new / {i} scanned] {ticker} ... +{total} rows", flush=True)
    print(f"raw_history_yahoo: +{total} rows from {processed} new files")
    return total


def ingest_yahoo_daily() -> int:
    """raw_daily_yahoo/yahoo_<DATE>.csv — daily snapshot."""
    folder = _folder("raw_daily_yahoo")
    if not folder:
        return 0
    total = 0
    # Numeric columns that occasionally hold stray "{}" / non-numeric junk.
    numeric_cols = ["Open", "High", "Low", "Close", "Volume", "Change",
                    "ChangePercent", "MarketCap", "SharesFloat", "SharesOutstanding",
                    "SharesShort", "SharesShortRatio", "SharesShortPercentOfFloat",
                    "SharesInsidersPercent", "SharesInstitutionsPercent", "Beta",
                    "TotalAssets", "NAV"]
    for f in sorted(folder.glob("*.csv")):
        try:
            df = pd.read_csv(f, index_col=0)
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        # Coerce numeric columns: junk like "{}" becomes NaN.
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.rename(columns={
            "Ticker": "ticker", "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume", "Change": "change",
            "ChangePercent": "change_pct", "Type": "quote_type",
            "MarketCap": "market_cap", "SharesFloat": "shares_float",
            "SharesOutstanding": "shares_outstanding", "SharesShort": "shares_short",
            "SharesShortRatio": "shares_short_ratio",
            "SharesShortPercentOfFloat": "shares_short_pct_float",
            "SharesInsidersPercent": "insiders_pct",
            "SharesInstitutionsPercent": "institutions_pct",
            "Beta": "beta", "TotalAssets": "total_assets", "NAV": "nav",
        })
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].astype(str).str.strip()
        total += writer.upsert_df(df, "raw_yahoo_daily", ["ticker", "date"])
    print(f"raw_daily_yahoo: {total} rows")
    return total


def ingest_fred() -> int:
    """raw_fred/<SERIES_ID>.csv — two cols: date, value (no header name)."""
    folder = _folder("raw_fred")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        series_id = f.stem
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index.name = "date"
            df = df.reset_index()
            df.columns = ["date", "value"]
            df["series_id"] = series_id
            df["date"] = df["date"].dt.date
        except Exception as exc:
            print(f"  skip {series_id}: {exc}")
            continue
        total += writer.upsert_df(df, "raw_fred", ["series_id", "date"])
    print(f"raw_fred: {total} rows")
    return total


def ingest_cpc() -> int:
    """data_cpc/<CATEGORY>.csv — appended rows, date as unnamed index."""
    folder = _folder("data_cpc")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        category = f.stem
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            df.index.name = "date"
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df["category"] = category
            df["date"] = df["date"].dt.date
        except Exception as exc:
            print(f"  skip {category}: {exc}")
            continue
        total += writer.upsert_df(df, "raw_cpc", ["category", "date"])
    print(f"data_cpc: {total} rows")
    return total


def ingest_finviz() -> int:
    """raw_daily_finviz/finviz_<DATE>.csv — ~70 site-native cols -> JSONB."""
    folder = _folder("raw_daily_finviz")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        try:
            df = pd.read_csv(f)
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        if "Ticker" not in df.columns or "Date" not in df.columns:
            continue
        date_str = str(df["Date"].iloc[0])
        indexed = {"Date", "Ticker", "Sector", "Industry", "Market Cap"}
        payload_cols = [c for c in df.columns if c not in indexed]
        rows = []
        for _, r in df.iterrows():
            rec = {
                "date": str(r.get("Date", date_str)),
                "ticker": str(r["Ticker"]).strip(),
                "sector": r.get("Sector"),
                "industry": r.get("Industry"),
                "market_cap": _to_float(r.get("Market Cap")),
            }
            for c in payload_cols:
                rec[c] = r[c]
            rows.append(rec)
        total += writer.upsert_jsonb_rows(
            "raw_finviz_daily", ["date", "ticker"], payload_cols, rows
        )
    print(f"raw_daily_finviz: {total} rows")
    return total


def ingest_short_finra() -> int:
    """raw_daily_short_finra/CNMSshvol<YYYYMMDD>.txt — pipe-delimited."""
    folder = _folder("raw_daily_short_finra")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.txt")):
        try:
            df = pd.read_csv(f, sep="|")
            # Drop the trailing summary row (Date isn't an 8-digit number there).
            df = df[df["Date"].astype(str).str.fullmatch(r"\d{8}")]
            df = df.rename(columns={
                "Date": "date_raw", "Symbol": "symbol",
                "ShortVolume": "short_volume", "ShortExemptVolume": "short_exempt_volume",
                "TotalVolume": "total_volume", "Market": "market",
            })
            df["date"] = pd.to_datetime(df["date_raw"], format="%Y%m%d").dt.date
            df = df.drop(columns=["date_raw"], errors="ignore")
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        total += writer.upsert_df(df, "raw_short_finra", ["symbol", "date", "market"])
    print(f"raw_daily_short_finra: {total} rows")
    return total


def ingest_bonds_bi() -> int:
    """raw_bonds_bi/bonds_<DATE>.csv — site-native cols -> JSONB."""
    folder = _folder("raw_bonds_bi")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        m = re.search(r"bonds_(\d{4}-\d{2}-\d{2})", f.name)
        date_str = m.group(1) if m else f.stem.replace("bonds_", "")
        try:
            df = pd.read_csv(f)
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        cols = list(df.columns)
        # Use Issuer+Coupon+Maturity as the synthetic bond id when present.
        def _id(r):
            parts = [str(r.get(c, "")) for c in ("Issuer", "Coupon", "Maturity Date") if c in r.index]
            return "|".join(parts) if any(parts) else str(r.name)
        rows = []
        for idx, r in df.iterrows():
            rec = {"date": str(date_str), "bond_id": _id(r)}
            for c in cols:
                rec[c] = r[c]
            rows.append(rec)
        total += writer.upsert_jsonb_rows("raw_bonds_bi", ["date", "bond_id"], cols, rows)
    print(f"raw_bonds_bi: {total} rows")
    return total


def ingest_bonds_finra() -> int:
    """raw_bonds_finra/bonds_<DATE>.csv — FINRA grid cols -> JSONB."""
    folder = _folder("raw_bonds_finra")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        m = re.search(r"bonds_(\d{4}-\d{2}-\d{2})", f.name)
        date_str = m.group(1) if m else f.stem.replace("bonds_", "")
        try:
            df = pd.read_csv(f, index_col=0)
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        cols = list(df.columns)
        id_col = "Symbol" if "Symbol" in cols else (cols[0] if cols else "id")
        rows = []
        for idx, r in df.iterrows():
            rec = {"date": str(date_str), "cusip": str(r.get(id_col, idx))}
            for c in cols:
                rec[c] = r[c]
            rows.append(rec)
        total += writer.upsert_jsonb_rows("raw_bonds_finra", ["date", "cusip"], cols, rows)
    print(f"raw_bonds_finra: {total} rows")
    return total


def ingest_etfdb_fundflow() -> int:
    """raw_etfdb_fundflow/<TICKER>.csv — Date, Fundflow."""
    folder = _folder("raw_etfdb_fundflow")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        ticker = f.stem
        try:
            df = pd.read_csv(f, parse_dates=["Date"])
            df = df.rename(columns={"Date": "date", "Fundflow": "fundflow"})
            df["ticker"] = ticker
            df["date"] = df["date"].dt.date
            df["fundflow"] = pd.to_numeric(df["fundflow"], errors="coerce")
        except Exception as exc:
            continue
        total += writer.upsert_df(df, "raw_etfdb_fundflow", ["ticker", "date"])
    print(f"raw_etfdb_fundflow: {total} rows")
    return total


def ingest_etfcom_fundflow() -> int:
    """raw_etfcom_fundflow/etf_fundflow_<DATE>.csv — Ticker,Date,Net Flows*.
    Also raw_etf_fundflow/ (same shape)."""
    total = 0
    for folder_name in ("raw_etfcom_fundflow", "raw_etf_fundflow"):
        folder = _folder(folder_name)
        if not folder:
            continue
        for f in sorted(folder.glob("*.csv")):
            try:
                df = pd.read_csv(f)
            except Exception:
                continue
            if "Ticker" not in df.columns:
                continue
            payload_cols = [c for c in df.columns if c not in ("Ticker", "Date")]
            rows = []
            for _, r in df.iterrows():
                if pd.isna(r.get("Ticker")) or str(r.get("Ticker")).strip() == "":
                    continue
                rec = {
                    "date": str(r.get("Date", f.stem.split("_")[-1])),
                    "ticker": str(r["Ticker"]).strip().upper(),
                }
                # Build the flows payload dict from all non-key columns.
                flows = {c: r[c] for c in payload_cols if not pd.isna(r[c])}
                rec["flows"] = flows
                rows.append(rec)
            if rows:
                # upsert_jsonb_rows expects (table, indexed_cols, payload_cols, rows)
                # but our schema names the JSONB column 'flows', not 'payload'.
                # Write directly via a small inline loop.
                from psycopg.types.json import Json
                from psycopg import sql as pgsql
                seen = {}
                for r in rows:
                    key = (r["date"], r["ticker"])
                    seen[key] = r
                records = list(seen.values())
                conflict = pgsql.SQL(" ON CONFLICT (date, ticker) DO UPDATE SET flows = EXCLUDED.flows")
                tuples = [(r["date"], r["ticker"], Json(r["flows"])) for r in records]
                BATCH = max(1, min(500, 65000 // 3))
                one_group = pgsql.SQL("({})").format(pgsql.SQL(", ").join([pgsql.Placeholder()] * 3))
                written = 0
                eng = writer.engine()
                for i in range(0, len(tuples), BATCH):
                    batch = tuples[i:i + BATCH]
                    groups = pgsql.SQL(", ").join([one_group] * len(batch))
                    args = [v for tup in batch for v in tup]
                    stmt = pgsql.SQL("INSERT INTO raw_etfcom_fundflow (date, ticker, flows) VALUES {vals}{conflict}").format(
                        vals=groups, conflict=conflict
                    )
                    with eng.begin() as conn:
                        with conn.connection.cursor() as cur:
                            cur.execute(stmt, args)
                    written += len(batch)
                total += written
    print(f"raw_etfcom_fundflow + raw_etf_fundflow: {total} rows")
    return total


def ingest_etfcom_holdings() -> int:
    """raw_etfcom_holdings/<TICKER>.csv — Name, Allocation (percent string)."""
    folder = _folder("raw_etfcom_holdings")
    if not folder:
        return 0
    today = pd.Timestamp.now().date()
    total = 0
    for f in sorted(folder.glob("*.csv")):
        ticker = f.stem
        try:
            df = pd.read_csv(f, index_col=0)
            df = df.rename(columns={"Name": "name", "Allocation": "allocation"})
            df["allocation"] = df["allocation"].astype(str).str.replace("%", "", regex=False)
            df["allocation"] = pd.to_numeric(df["allocation"], errors="coerce")
            df["ticker"] = ticker
            df["date"] = str(today)  # holdings snapshot date unknown; use ingest date
            df = df.reset_index(drop=True)
        except Exception as exc:
            continue
        total += writer.upsert_df(df, "raw_etf_holdings", ["ticker", "date", "name"])
    print(f"raw_etfcom_holdings: {total} rows")
    return total


def ingest_macrotrends() -> int:
    """raw_history_macrotrends/MacroTrends_Data_Download_<TICKER>.csv.
    Multi-line header; data table starts after a blank line."""
    folder = _folder("raw_history_macrotrends")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        m = re.search(r"Download_([A-Z.]+)", f.stem)
        ticker = m.group(1) if m else f.stem
        try:
            # Find the header row (the one starting with 'date').
            raw = f.read_text(encoding="utf-8", errors="replace").splitlines()
            header_idx = None
            for i, line in enumerate(raw):
                if line.lower().startswith("date,"):
                    header_idx = i
                    break
            if header_idx is None:
                continue
            df = pd.read_csv(io.StringIO("\n".join(raw[header_idx:])))
            df = df.rename(columns=lambda c: c.strip().lower().replace(" ", "_"))
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df = df.dropna(subset=["date"])
            df = df.rename(columns={
                "open": "adj_open", "high": "adj_high", "low": "adj_low",
                "close": "adj_close", "market_cap": "market_cap",
            })
            df["ticker"] = ticker
        except Exception as exc:
            print(f"  skip {ticker}: {exc}")
            continue
        total += writer.upsert_df(df, "raw_macrotrends_history", ["ticker", "date"])
    print(f"raw_history_macrotrends: {total} rows")
    return total


def ingest_eoddata() -> int:
    """raw_daily_eoddata/eoddata_<DATE>.csv — Symbol, Date, OHLCV, Exchange."""
    folder = _folder("raw_daily_eoddata")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("eoddata_*.csv")):
        # Skip per-exchange files (eoddata_<EXCHANGE>_<DATE>.csv).
        parts = f.stem.replace("eoddata_", "").split("_")
        if len(parts) == 2:
            continue
        try:
            df = pd.read_csv(f, index_col=0)
            df = df.rename(columns={
                "Symbol": "ticker", "Date": "date",
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume", "Exchange": "exchange",
            })
            df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce").dt.date
            df = df.dropna(subset=["date"])
        except Exception as exc:
            print(f"  skip {f.name}: {exc}")
            continue
        total += writer.upsert_df(df, "raw_eoddata_daily", ["ticker", "date", "exchange"])
    print(f"raw_daily_eoddata: {total} rows")
    return total


def ingest_etf_reconciled() -> int:
    """data_etf/<TICKER>.csv — the legacy reconciled ETF output. Goes into
    reconcile_price_history so the UI has reconciled history available."""
    folder = _folder("data_etf")
    if not folder:
        return 0
    total = 0
    for f in sorted(folder.glob("*.csv")):
        ticker = f.stem
        try:
            df = pd.read_csv(f, parse_dates=["Date"])
            df = df.rename(columns={
                "Date": "date", "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "AdjOpen": "adj_open", "AdjHigh": "adj_high",
                "AdjLow": "adj_low", "AdjClose": "adj_close", "Volume": "volume",
                "Dividend": "dividend", "Split": "split_ratio",
                "SplitFactor": "split_factor", "FundFlow": "fundflow",
            })
            df["ticker"] = ticker
            df["date"] = df["date"].dt.date
            df["source_count"] = 0  # legacy reconcile didn't track sources
            df["sources"] = [None] * len(df)
        except Exception as exc:
            continue
        total += writer.upsert_df(df, "reconcile_price_history", ["ticker", "date"])
    print(f"data_etf (legacy reconcile): {total} rows")
    return total


# ---------------------------------------------------------------------------
# Registry + CLI
# ---------------------------------------------------------------------------
LOADERS = {
    "yahoo_history": ingest_yahoo_history,
    "yahoo_daily": ingest_yahoo_daily,
    "fred": ingest_fred,
    "cpc": ingest_cpc,
    "finviz": ingest_finviz,
    "short_finra": ingest_short_finra,
    "bonds_bi": ingest_bonds_bi,
    "bonds_finra": ingest_bonds_finra,
    "etfdb_fundflow": ingest_etfdb_fundflow,
    "etfcom_fundflow": ingest_etfcom_fundflow,
    "etfcom_holdings": ingest_etfcom_holdings,
    "macrotrends": ingest_macrotrends,
    "eoddata": ingest_eoddata,
    "etf_reconciled": ingest_etf_reconciled,
}


def main(source: str = "all") -> int:
    if source == "all":
        for name, fn in LOADERS.items():
            print(f"\n=== {name} ===")
            try:
                fn()
            except Exception as exc:
                print(f"  FAILED: {exc}")
    elif source in LOADERS:
        LOADERS[source]()
    else:
        print(f"unknown source '{source}'. available: {list(LOADERS)} + 'all'")
        return 1
    return 0


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "all"
    sys.exit(main(src))
