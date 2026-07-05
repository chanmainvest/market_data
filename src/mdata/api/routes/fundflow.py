"""ETF fund flow: etfdb (numeric series) + etfcom (JSONB snapshot)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/fundflow/{ticker}")
def fundflow(
    ticker: str,
    source: str = Query("etfdb", help="etfdb | etfcom"),
    limit: int = Query(5000, ge=1, le=20000),
) -> dict:
    t = ticker.upper()
    if source == "etfdb":
        with engine().connect() as conn:
            rows = conn.execute(
                text("""SELECT date, fundflow FROM raw_etfdb_fundflow
                        WHERE ticker = :t ORDER BY date LIMIT :limit"""),
                {"t": t, "limit": limit},
            ).fetchall()
        return {"ticker": t, "source": "etfdb", "count": len(rows),
                "rows": [{"date": str(r[0]), "fundflow": r[1]} for r in rows]}

    if source == "etfcom":
        with engine().connect() as conn:
            rows = conn.execute(
                text("""SELECT date, flows FROM raw_etfcom_fundflow
                        WHERE ticker = :t ORDER BY date LIMIT :limit"""),
                {"t": t, "limit": limit},
            ).mappings().all()
        return {"ticker": t, "source": "etfcom", "count": len(rows),
                "rows": [dict(r) for r in rows]}

    return {"error": f"unknown source '{source}'"}


@router.get("/holdings/{ticker}")
def holdings(
    ticker: str,
    limit: int = Query(1000, ge=1, le=10000),
) -> dict:
    """ETF.com holdings snapshots for a ticker."""
    t = ticker.upper()
    with engine().connect() as conn:
        rows = conn.execute(
            text("""SELECT date, name, allocation FROM raw_etf_holdings
                    WHERE ticker = :t ORDER BY date DESC, allocation DESC NULLS LAST
                    LIMIT :limit"""),
            {"t": t, "limit": limit},
        ).mappings().all()
    return {"ticker": t, "count": len(rows), "items": [dict(r) for r in rows]}
