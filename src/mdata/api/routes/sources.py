"""Source registry + freshness: GET /api/health, GET /api/sources."""
from __future__ import annotations

from collections import namedtuple

from fastapi import APIRouter
from sqlalchemy import text

from ...db import engine, test_connection

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "db": test_connection()}


# Each source: (display name, table, freshness column). The freshness column
# is the one written when a scraper upserts a row; we max() it to show when
# the source was last touched.
_Source = namedtuple("_Source", ["name", "table", "freshness_col"])
_SOURCE_TABLES = [
    _Source("yahoo_daily",         "raw_yahoo_daily",            "scraped_at"),
    _Source("yahoo_history",       "raw_yahoo_history",          "scraped_at"),
    _Source("yahoo_earnings",      "raw_yahoo_earnings",         "scraped_at"),
    _Source("alpha_vantage",       "raw_alpha_vantage_history",  "scraped_at"),
    _Source("macrotrends",         "raw_macrotrends_history",    "scraped_at"),
    _Source("eoddata",             "raw_eoddata_daily",          "scraped_at"),
    _Source("fred",                "raw_fred",                   "scraped_at"),
    _Source("finviz",              "raw_finviz_daily",           "scraped_at"),
    _Source("cpc",                 "raw_cpc",                    "scraped_at"),
    _Source("short_finra",         "raw_short_finra",            "scraped_at"),
    _Source("bonds_bi",            "raw_bonds_bi",               "scraped_at"),
    _Source("bonds_finra",         "raw_bonds_finra",            "scraped_at"),
    _Source("etfdb_fundflow",      "raw_etfdb_fundflow",         "scraped_at"),
    _Source("etfcom_fundflow",     "raw_etfcom_fundflow",        "scraped_at"),
    _Source("reconcile_prices",    "reconcile_price_history",    "reconciled_at"),
]


@router.get("/sources")
def sources() -> list[dict]:
    """Approximate row count + latest-scrape time per data source.

    Both metrics are designed to be fast on multi-million-row TimescaleDB
    hypertables. Exact ``count(*)`` and unconstrained ``max(scraped_at)``
    are far too slow here (e.g. raw_yahoo_history has 33M rows across 5000
    chunks; a full scan + 5000-chunk plan takes ~20 s).

    Row counts are *approximate* (planner stats, not ``count(*)``). Two
    TimescaleDB gotchas apply:

    1. The hypertable parent's ``reltuples`` is always 0 — stats live on
       the chunk child tables.
    2. Compressed chunks always report ``reltuples = -1`` (their data was
       rewritten into a separate compressed table), so naively summing
       chunk ``reltuples`` over a heavily-compressed table produces a large
       *negative* number. The pre-compression row count is stored in
       ``compression_chunk_size.numrows_pre_compression`` instead.

    So the count is: ``sum(uncompressed-chunk reltuples)`` clamped to >= 0,
    plus ``sum(compressed-chunk numrows_pre_compression)``.

    ``last_scraped`` comes from ``max(freshness_col)`` over the *most recent
    chunk only*. Querying the parent hypertable directly is prohibitively
    expensive here: even with a time-range predicate that triggers chunk
    exclusion, planning a query over thousands of chunks takes ~18 s on
    raw_yahoo_history alone. So instead we look up the newest chunk's
    physical table name from the TimescaleDB catalog and run ``max()`` on
    that one chunk directly (~0.1 ms). Because rows are written in
    chronological order, the newest chunk holds the newest data; if it
    happens to be empty we walk back through the previous chunks.
    """
    out: list[dict] = []
    with engine().connect() as conn:
        for src in _SOURCE_TABLES:
            approx = conn.execute(
                text(
                    """
                    SELECT COALESCE(
                        -- uncompressed chunks: sum their reltuples (>= 0)
                        (SELECT COALESCE(sum(GREATEST(uc.reltuples, 0)), 0)::bigint
                         FROM _timescaledb_catalog.hypertable hh
                         JOIN _timescaledb_catalog.chunk ch
                           ON ch.hypertable_id = hh.id AND ch.dropped = false
                         LEFT JOIN pg_class uc
                           ON uc.oid = (ch.schema_name||'.'||ch.table_name)::regclass
                         WHERE hh.table_name = :t
                           AND ch.compressed_chunk_id IS NULL)
                        +
                        -- compressed chunks: reltuples is -1; use the row
                        -- count captured at compression time
                        (SELECT COALESCE(sum(ccs.numrows_pre_compression), 0)::bigint
                         FROM _timescaledb_catalog.hypertable hh
                         JOIN _timescaledb_catalog.chunk ch
                           ON ch.hypertable_id = hh.id AND ch.dropped = false
                         JOIN _timescaledb_catalog.compression_chunk_size ccs
                           ON ccs.chunk_id = ch.id
                         WHERE hh.table_name = :t),
                        -- not a hypertable: fall back to plain reltuples
                        (SELECT GREATEST(reltuples, 0)::bigint
                         FROM pg_class WHERE relname = :t),
                        0
                    )
                    """
                ),
                {"t": src.table},
            ).scalar()

            # Freshness: max(freshness_col) over the most recent non-empty
            # chunk. Walk back through the newest few chunks (creation_time
            # DESC) until one yields a non-null max. Avoids the multi-second
            # planning cost of touching the hypertable parent.
            last_scraped = None
            chunk_rows = conn.execute(
                text(
                    """
                    SELECT quote_ident(ch.schema_name) || '.' || quote_ident(ch.table_name) AS rel
                    FROM _timescaledb_catalog.chunk ch
                    JOIN _timescaledb_catalog.hypertable h ON ch.hypertable_id = h.id
                    WHERE h.table_name = :t AND ch.dropped = false
                    ORDER BY ch.creation_time DESC
                    LIMIT 10
                    """
                ),
                {"t": src.table},
            ).fetchall()
            for (rel,) in chunk_rows:
                val = conn.execute(
                    text(f"SELECT max({src.freshness_col}) FROM {rel}")
                ).scalar()
                if val is not None:
                    last_scraped = val
                    break

            # Fall back to a plain table scan (non-hypertable) if no chunk.
            if last_scraped is None and not chunk_rows:
                last_scraped = conn.execute(
                    text(f"SELECT max({src.freshness_col}) FROM {src.table}")
                ).scalar()

            out.append({
                "source": src.name,
                "table": src.table,
                "rows": int(approx or 0),
                "rows_exact": False,
                "last_scraped": last_scraped.isoformat() if last_scraped else None,
            })
    return out


@router.get("/sources/{source_name}")
def source_detail(source_name: str) -> dict:
    """Exact row count + last-scraped timestamp for a single source.

    This does a real ``count(*)`` + ``max(ts)`` so it's slower than the
    listing endpoint — call it only when you need precise freshness for one
    source.
    """
    match = next((s for s in _SOURCE_TABLES if s.name == source_name), None)
    if not match:
        return {"error": f"unknown source '{source_name}'",
                "available": [s.name for s in _SOURCE_TABLES]}
    with engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT count(*) AS n, max({match.freshness_col}) AS last_ts "
                f"FROM {match.table}"
            )
        ).fetchone()
    return {
        "source": source_name,
        "table": match.table,
        "rows": int(row[0] or 0),
        "rows_exact": True,
        "last_scraped": str(row[1]) if row[1] else None,
    }
