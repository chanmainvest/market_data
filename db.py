#!/usr/bin/env python
"""Shared Postgres writer helpers for the market_data scrapers.

Behavior
--------
- If the env var ``MARKET_DATA_DB=1`` is set, every call connects to Postgres
  and upserts. Otherwise every call is a silent no-op — scrapers stay
  CSV-only and the legacy git-push pipeline keeps working.
- Connection details come from ``MARKET_DATA_DB_URL`` if present, otherwise
  are built from the individual ``POSTGRES_*`` env vars.
- Upserts use ``INSERT ... ON CONFLICT (...) DO UPDATE`` so re-runs are
  idempotent.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Sequence

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

_engine = None
_metadata = None
_table_cache: dict[str, Table] = {}


def _db_enabled() -> bool:
    return os.environ.get('MARKET_DATA_DB', '').strip() in ('1', 'true', 'TRUE', 'yes')


def _build_url() -> str:
    explicit = os.environ.get('MARKET_DATA_DB_URL')
    if explicit:
        return explicit
    user = os.environ.get('POSTGRES_USER', 'mdata')
    pw = os.environ.get('POSTGRES_PASSWORD', 'mdata')
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5433')
    db = os.environ.get('POSTGRES_DB', 'mdata')
    return f'postgresql+psycopg://{user}:{pw}@{host}:{port}/{db}'


def engine():
    """Return a cached SQLAlchemy engine, or None if DB writing is disabled."""
    global _engine, _metadata
    if not _db_enabled():
        return None
    if _engine is None:
        _engine = create_engine(_build_url(), pool_pre_ping=True, future=True)
        _metadata = MetaData()
    return _engine


def _get_table(name: str) -> Table:
    """Return a reflected SQLAlchemy Table for ``name`` (cached)."""
    eng = engine()
    if name not in _table_cache:
        _table_cache[name] = Table(name, _metadata, autoload_with=eng)
    return _table_cache[name]


def _normalize_value(v):
    """Convert pandas/numpy scalar to a JSON/SQL-friendly Python value."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if hasattr(v, 'item'):                       # numpy scalar
        try:
            return v.item()
        except Exception:
            return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def upsert_df(
    df: pd.DataFrame,
    table: str,
    conflict_cols: Sequence[str],
) -> int:
    """Upsert a DataFrame into ``table`` keyed by ``conflict_cols``.

    Returns the number of rows written (0 if DB is disabled or df is empty).
    Columns in the DataFrame that do not exist in the target table are
    silently dropped to keep the scrapers resilient to schema drift.
    """
    eng = engine()
    if eng is None or df is None or df.empty:
        return 0

    df = df.copy()
    # Normalize column names: lowercase, no spaces (matches our SQL naming).
    df.columns = [str(c).strip().lower().replace(' ', '_').replace('.', '_').replace('-', '_') for c in df.columns]
    conflict_cols = [str(c).lower() for c in conflict_cols]

    # Reset any named index into columns so it gets written too.
    if df.index.name is not None:
        df = df.reset_index()
        df.rename(columns={df.index.name: str(df.index.name).lower()}, inplace=True)

    # Intersect with the actual table columns to avoid schema-mismatch errors.
    with eng.connect() as conn:
        col_rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {'t': table},
        ).fetchall()
        table_cols = {r[0] for r in col_rows}
    df = df[[c for c in df.columns if c in table_cols]]
    if df.empty or not any(c in conflict_cols for c in df.columns):
        return 0

    # Drop intra-batch duplicates on the conflict key (keep last) — Postgres
    # ON CONFLICT only dedupes against existing rows, not within a single
    # INSERT statement, so a daily snapshot file with repeated ticker+date
    # would otherwise raise "ON CONFLICT DO UPDATE command cannot affect row
    # a second time".
    df = df.drop_duplicates(subset=conflict_cols, keep="last")

    records = [
        {c: _normalize_value(row[c]) for c in df.columns}
        for _, row in df.iterrows()
    ]
    update_cols = [c for c in df.columns if c not in conflict_cols]
    cols = list(df.columns)
    tuples = [tuple(r[c] for c in cols) for r in records]

    # Build the ON CONFLICT clause once.
    from psycopg import sql as pgsql
    if update_cols:
        set_clause = pgsql.SQL(", ").join(
            pgsql.SQL("{c} = EXCLUDED.{c}").format(c=pgsql.Identifier(c))
            for c in update_cols
        )
        conflict_target = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in conflict_cols)
        on_conflict = pgsql.SQL(" ON CONFLICT ({targets}) DO UPDATE SET {set}").format(
            targets=conflict_target, set=set_clause
        )
    else:
        conflict_target = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in conflict_cols)
        on_conflict = pgsql.SQL(" ON CONFLICT ({targets}) DO NOTHING").format(
            targets=conflict_target
        )

    one_row_ph = pgsql.SQL(", ").join(pgsql.Placeholder() * len(cols))
    insert_one = pgsql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({ph}){conflict}").format(
        tbl=pgsql.Identifier(table),
        cols=pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
        ph=one_row_ph,
        conflict=on_conflict,
    )

    # Multi-row VALUES per statement, batched to stay under Postgres's 65535
    # bind-param cap (floor(65535/n_cols)) and committed per batch to avoid
    # exhausting shared memory on very large frames.
    n_cols = max(len(cols), 1)
    BATCH = max(1, min(500, 65000 // n_cols))
    one_group = pgsql.SQL("({})").format(pgsql.SQL(", ").join([pgsql.Placeholder()] * n_cols))
    written = 0
    for i in range(0, len(tuples), BATCH):
        batch = tuples[i:i + BATCH]
        groups = pgsql.SQL(", ").join([one_group] * len(batch))
        args = [v for tup in batch for v in tup]
        stmt = pgsql.SQL("INSERT INTO {tbl} ({cols}) VALUES {vals}{conflict}").format(
            tbl=pgsql.Identifier(table),
            cols=pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
            vals=groups,
            conflict=on_conflict,
        )
        with eng.begin() as conn:
            with conn.connection.cursor() as cur:
                cur.execute(stmt, args)
        written += len(batch)
    return written


def upsert_jsonb_rows(
    table: str,
    indexed_cols: Sequence[str],
    payload_cols: Sequence[str],
    rows: Iterable[dict],
) -> int:
    """Upsert rows whose variable-width fields are bundled into a JSONB
    ``payload`` column. ``indexed_cols`` are top-level columns that form the
    conflict key; everything in ``payload_cols`` is serialized into JSONB.

    Returns the number of rows written (0 if DB disabled or rows empty).
    """
    eng = engine()
    if eng is None:
        return 0
    rows = list(rows)
    if not rows:
        return 0

    indexed_cols = [str(c).lower() for c in indexed_cols]
    payload_cols = [str(c).lower() for c in payload_cols]

    # Dedupe on the conflict key (keep last) within the batch.
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = tuple(_normalize_value(r.get(c)) for c in indexed_cols)
        rec = {c: _normalize_value(r.get(c)) for c in indexed_cols}
        from psycopg.types.json import Json
        rec['payload'] = Json(
            {k: _normalize_value(v) for k, v in r.items() if k.lower() in payload_cols}
        )
        seen[key] = rec
    records = list(seen.values())
    if not records:
        return 0

    cols = indexed_cols + ['payload']
    tuples = [tuple(rec[c] for c in cols) for rec in records]

    from psycopg import sql as pgsql
    conflict_target = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in indexed_cols)
    on_conflict = pgsql.SQL(" ON CONFLICT ({targets}) DO UPDATE SET payload = EXCLUDED.payload").format(
        targets=conflict_target
    )

    n_cols = len(cols)
    BATCH = max(1, min(500, 65000 // n_cols))
    one_group = pgsql.SQL("({})").format(pgsql.SQL(", ").join([pgsql.Placeholder()] * n_cols))
    written = 0
    for i in range(0, len(tuples), BATCH):
        batch = tuples[i:i + BATCH]
        groups = pgsql.SQL(", ").join([one_group] * len(batch))
        args = [v for tup in batch for v in tup]
        stmt = pgsql.SQL("INSERT INTO {tbl} ({cols}) VALUES {vals}{conflict}").format(
            tbl=pgsql.Identifier(table),
            cols=pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
            vals=groups,
            conflict=on_conflict,
        )
        with eng.begin() as conn:
            with conn.connection.cursor() as cur:
                cur.execute(stmt, args)
        written += len(batch)
    return written
