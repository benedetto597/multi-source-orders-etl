"""Profile the source database before designing (or re-checking) the ETL."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select


def _header(title: str, width: int = 80) -> list[str]:
    return ["", "=" * width, title.center(width), "=" * width]


def explore_source(url: str) -> str:
    """Return a text report: tables, column types, row counts, samples, date ranges, dup ids.

    Queries are built with SQLAlchemy Core, so they render correctly for SQLite and SQL Server
    (``LIMIT`` vs ``TOP``, identifier quoting).
    """
    engine = create_engine(url)
    out = _header(f"SOURCE EXPLORATION - {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        tables = sorted(inspect(engine).get_table_names())
        out += _header(f"TABLES FOUND: {len(tables)}")
        out += tables
        metadata = MetaData()
        with engine.connect() as conn:
            for name in tables:
                tbl = Table(name, metadata, autoload_with=conn)
                out += _header(f"TABLE: {name}")
                schema = pd.DataFrame(
                    {
                        "column": [c.name for c in tbl.columns],
                        "type": [str(c.type) for c in tbl.columns],
                        "nullable": [c.nullable for c in tbl.columns],
                    }
                )
                out += ["", "SCHEMA:", schema.to_string(index=False)]
                total = conn.execute(select(func.count()).select_from(tbl)).scalar_one()
                out.append(f"\nRows: {total:,}")
                sample = pd.read_sql(select(tbl).limit(5), conn)
                out += ["", "SAMPLE (5 rows):", sample.to_string(index=False)]
                if "created_at" in tbl.c:
                    lo, hi = conn.execute(
                        select(func.min(tbl.c.created_at), func.max(tbl.c.created_at))
                    ).one()
                    out.append(f"\ncreated_at range: {lo} .. {hi}")
                if "id" in tbl.c:
                    dup_ids = (
                        select(tbl.c.id).group_by(tbl.c.id).having(func.count() > 1).subquery()
                    )
                    dups = conn.execute(select(func.count()).select_from(dup_ids)).scalar_one()
                    out.append(f"Duplicate ids: {dups}")
    finally:
        engine.dispose()
    return "\n".join(out)
