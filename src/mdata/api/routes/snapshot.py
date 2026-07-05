"""Daily snapshot endpoints (wide/site-native rows)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/snapshot/{date}")
def snapshot(
    date: str,
    source: str = Query("finviz", help="finviz | yahoo | eoddata"),
    sector: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    if source == "finviz":
        where = "date = :d"
        params: dict = {"d": date, "limit": limit}
        if sector:
            where += " AND sector = :sector"
            params["sector"] = sector
        with engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"""SELECT date, ticker, sector, industry, market_cap, payload
                        FROM raw_finviz_daily WHERE {where}
                        ORDER BY ticker LIMIT :limit"""
                ),
                params,
            ).mappings().all()
        return {"date": date, "source": "finviz", "count": len(rows),
                "items": [dict(r) for r in rows]}

    if source == "yahoo":
        with engine().connect() as conn:
            rows = conn.execute(
                text("""SELECT * FROM raw_yahoo_daily WHERE date = :d
                        ORDER BY market_cap DESC NULLS LAST LIMIT :limit"""),
                {"d": date, "limit": limit},
            ).mappings().all()
        return {"date": date, "source": "yahoo", "count": len(rows),
                "items": [dict(r) for r in rows]}

    if source == "eoddata":
        with engine().connect() as conn:
            rows = conn.execute(
                text("""SELECT * FROM raw_eoddata_daily WHERE date = :d
                        ORDER BY ticker LIMIT :limit"""),
                {"d": date, "limit": limit},
            ).mappings().all()
        return {"date": date, "source": "eoddata", "count": len(rows),
                "items": [dict(r) for r in rows]}

    return {"error": f"unknown source '{source}'"}
