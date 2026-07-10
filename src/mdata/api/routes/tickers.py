"""Ticker reference + search: GET /api/tickers, GET /api/tickers/{ticker}."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/tickers/suggest")
def suggest_ticker(q: str = Query(..., min_length=1, max_length=20)) -> dict:
    """Suggest similar tickers via levenshtein distance (fuzzystrmatch).

    Used by the UI for a "Did you mean ...?" hint when a search lands on a
    ticker that has no data. Draws candidates from the distinct tickers
    actually present in raw_yahoo_history (the largest raw table), not from
    the (currently empty) ref_ticker reference table.
    """
    needle = q.upper().strip()
    with engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ticker, levenshtein(ticker, :q) AS dist
                FROM (SELECT DISTINCT ticker FROM raw_yahoo_history) t
                WHERE ticker <> :q
                ORDER BY dist ASC, ticker
                LIMIT 8
                """
            ),
            {"q": needle},
        ).fetchall()
    return {
        "query": needle,
        "suggestions": [{"ticker": r[0], "distance": r[1]} for r in rows],
    }


@router.get("/tickers")
def list_tickers(
    q: str | None = Query(None, help="Substring search on ticker / description"),
    type: str | None = Query(None, help="Filter by type: stock | etf | index"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Search the unified ticker universe."""
    clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if q:
        clauses.append("(LOWER(ticker) LIKE :q OR LOWER(COALESCE(description,'')) LIKE :q)")
        params["q"] = f"%{q.lower()}%"
    if type:
        clauses.append("type = :type")
        params["type"] = type
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with engine().connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM ref_ticker {where}"), params).scalar()
        rows = conn.execute(
            text(
                f"""SELECT ticker, type, description, w_sp500, w_nasdaq100, w_dowjones,
                           earnings_report_time, updated_at
                    FROM ref_ticker {where}
                    ORDER BY ticker LIMIT :limit OFFSET :offset"""
            ),
            params,
        ).mappings().all()
    return {"total": int(total or 0), "items": [dict(r) for r in rows]}


@router.get("/tickers/{ticker}")
def ticker_detail(ticker: str) -> dict:
    """Reference info + latest snapshot per source for one ticker."""
    out: dict = {"ticker": ticker.upper()}
    with engine().connect() as conn:
        # reference
        ref = conn.execute(
            text("""SELECT * FROM ref_ticker WHERE ticker = :t"""),
            {"t": ticker.upper()},
        ).mappings().first()
        out["reference"] = dict(ref) if ref else None

        # etfdb / etfcom descriptor
        etfdb = conn.execute(
            text("SELECT description, info FROM ref_etfdb_info WHERE ticker = :t"),
            {"t": ticker.upper()},
        ).mappings().first()
        out["etfdb_info"] = dict(etfdb) if etfdb else None
        etfcom = conn.execute(
            text("SELECT description, info FROM ref_etfcom_info WHERE ticker = :t"),
            {"t": ticker.upper()},
        ).mappings().first()
        out["etfcom_info"] = dict(etfcom) if etfcom else None

        # latest row from each raw source
        for label, table in (
            ("yahoo_history", "raw_yahoo_history"),
            ("alpha_vantage", "raw_alpha_vantage_history"),
            ("macrotrends", "raw_macrotrends_history"),
            ("yahoo_daily", "raw_yahoo_daily"),
            ("reconciled", "reconcile_price_history"),
        ):
            row = conn.execute(
                text(f"SELECT * FROM {table} WHERE ticker = :t ORDER BY date DESC LIMIT 1"),
                {"t": ticker.upper()},
            ).mappings().first()
            out[label] = dict(row) if row else None
    return out
