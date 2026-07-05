"""Earnings calendar: GET /api/earnings?week=YYYY-MM-DD"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/earnings")
def earnings(
    week: str | None = Query(None, description="Monday of the week, YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    clauses = []
    params: dict = {"limit": limit}
    if week:
        clauses.append("earnings_week_monday = :w")
        params["w"] = week
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine().connect() as conn:
        rows = conn.execute(
            text(f"""SELECT * FROM raw_yahoo_earnings {where}
                    ORDER BY earnings_date, ticker LIMIT :limit"""),
            params,
        ).mappings().all()
    return {"count": len(rows), "items": [dict(r) for r in rows]}
