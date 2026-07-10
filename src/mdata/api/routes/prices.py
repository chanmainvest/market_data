"""Price history endpoints.

GET /api/prices/{ticker}?source=&start=&end=        — OHLC from one raw source
GET /api/prices/{ticker}/reconciled?start=&end=      — reconciled OHLC + source_count
GET /api/prices/{ticker}/compare?start=&end=         — all sources side-by-side
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()

# Map the ?source= query value to its table.
_SOURCE_TABLES = {
    "yahoo": "raw_yahoo_history",
    "alpha_vantage": "raw_alpha_vantage_history",
    "macrotrends": "raw_macrotrends_history",
    "eoddata": "raw_eoddata_daily",
}


@router.get("/prices/{ticker}")
def prices(
    ticker: str,
    source: str = Query("reconciled", help="yahoo | alpha_vantage | macrotrends | reconciled"),
    start: str | None = Query(None, help="YYYY-MM-DD"),
    end: str | None = Query(None, help="YYYY-MM-DD"),
    limit: int = Query(5000, ge=1, le=20000),
) -> dict:
    table = "reconcile_price_history" if source == "reconciled" else _SOURCE_TABLES.get(source)
    if table is None:
        return {"error": f"unknown source '{source}'", "available": list(_SOURCE_TABLES) + ["reconciled"]}

    clauses = ["ticker = :t"]
    params: dict = {"t": ticker.upper(), "limit": limit}
    if start:
        clauses.append("date >= :start")
        params["start"] = start
    if end:
        clauses.append("date <= :end")
        params["end"] = end
    where = " AND ".join(clauses)

    # Take the most recent `limit` rows (ORDER BY date DESC) then re-sort
    # ascending so the chart renders left-to-right chronologically. Without
    # the inner DESC a plain `ORDER BY date LIMIT n` returns the *oldest* n
    # rows — useless for a long-history ticker like AAPL (11k rows).
    with engine().connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT * FROM ("
                f"  SELECT * FROM {table} WHERE {where} ORDER BY date DESC LIMIT :limit"
                f") recent ORDER BY date"
            ),
            params,
        ).mappings().all()
    return {"ticker": ticker.upper(), "source": source, "count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/prices/{ticker}/reconciled")
def reconciled(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(5000, ge=1, le=20000),
) -> dict:
    return prices(ticker, source="reconciled", start=start, end=end, limit=limit)


@router.get("/prices/{ticker}/compare")
def compare(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(2000, ge=1, le=10000),
) -> dict:
    """Side-by-side close prices across all sources + reconciled, for charting."""
    series: dict = {}
    params: dict = {"t": ticker.upper(), "limit": limit}
    date_clause = ""
    if start:
        date_clause += " AND date >= :start"
        params["start"] = start
    if end:
        date_clause += " AND date <= :end"
        params["end"] = end

    with engine().connect() as conn:
        for label, table, close_col in (
            ("yahoo", "raw_yahoo_history", "close"),
            ("alpha_vantage", "raw_alpha_vantage_history", "close"),
            ("macrotrends", "raw_macrotrends_history", "close"),
            ("reconciled", "reconcile_price_history", "close"),
        ):
            # Most recent `limit` rows, re-sorted ascending (see prices()).
            rows = conn.execute(
                text(
                    f"SELECT d, c FROM ("
                    f"  SELECT date AS d, {close_col} AS c FROM {table} "
                    f"  WHERE ticker = :t{date_clause} ORDER BY date DESC LIMIT :limit"
                    f") recent ORDER BY d"
                ),
                params,
            ).fetchall()
            series[label] = [
                {"date": str(r[0]), "close": float(r[1]) if r[1] is not None else None}
                for r in rows
            ]
    return {"ticker": ticker.upper(), "series": series}
