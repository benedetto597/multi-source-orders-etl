"""Load the consolidated orders into SQLite: atomic full refresh or upsert."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from orders_etl.schema import (
    CREATE_QUARANTINE_SQL,
    CREATE_TABLE_SQL,
    INDEXES_SQL,
    QUARANTINE_COLUMNS,
    QUARANTINE_TABLE,
    TARGET_COLUMNS,
    TARGET_TABLE,
)

logger = logging.getLogger(__name__)

_KEY = ("id", "distribution_center")
_PLACEHOLDERS = ", ".join("?" for _ in TARGET_COLUMNS)
_INSERT_SQL = f"INSERT INTO {TARGET_TABLE} ({', '.join(TARGET_COLUMNS)}) VALUES ({_PLACEHOLDERS})"
_UPDATABLE = [c for c in TARGET_COLUMNS if c not in (*_KEY, "loaded_at")]
# Latest-wins also against the target: an older re-delivery never overwrites a newer row.
_UPSERT_SQL = (
    f"{_INSERT_SQL} ON CONFLICT(id, distribution_center) DO UPDATE SET "
    + ", ".join(f"{c} = excluded.{c}" for c in _UPDATABLE)
    + " WHERE COALESCE(excluded.updated_at, excluded.created_at, '')"
    f" >= COALESCE({TARGET_TABLE}.updated_at, {TARGET_TABLE}.created_at, '')"
)


@dataclass(frozen=True)
class UpsertStats:
    inserted: int
    updated: int
    skipped_stale: int = 0


@dataclass(frozen=True)
class LoadSummary:
    total: int
    by_dc: dict[str, int]
    by_source: dict[str, int]
    duplicate_keys: int


def _to_sql_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, datetime):  # also covers pd.Timestamp
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float) and value != value:  # NaN
        return None
    if hasattr(value, "item"):  # numpy scalar -> python scalar
        return value.item()
    return value


def _records(df: pd.DataFrame, columns: tuple[str, ...] = TARGET_COLUMNS) -> list[tuple]:
    frame = df.reindex(columns=list(columns)).astype(object)
    return [tuple(_to_sql_value(v) for v in row) for row in frame.itertuples(index=False)]


class SqliteLoader:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """One connection, one transaction: commit on success, roll back on any error."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            yield conn

    def create_table(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.execute(CREATE_TABLE_SQL)
            for sql in INDEXES_SQL:
                conn.execute(sql)
            conn.execute(CREATE_QUARANTINE_SQL)

    def replace_all(self, df: pd.DataFrame) -> int:
        """Full refresh. DELETE and INSERT share a transaction, so a failure keeps the old data."""
        rows = _records(df)
        with self._transaction() as conn:
            conn.execute(f"DELETE FROM {TARGET_TABLE}")
            conn.executemany(_INSERT_SQL, rows)
        logger.info("Full refresh loaded %s rows", f"{len(rows):,}")
        return len(rows)

    def upsert(self, df: pd.DataFrame) -> UpsertStats:
        """Insert new keys and update existing ones (``loaded_at`` keeps the first load time)."""
        rows = _records(df)
        with self._transaction() as conn:
            existing = set(conn.execute(f"SELECT id, distribution_center FROM {TARGET_TABLE}"))
            matched = sum((r[0], r[1]) in existing for r in rows)
            before = conn.total_changes
            conn.executemany(_UPSERT_SQL, rows)
            changed = conn.total_changes - before
        inserted = len(rows) - matched
        updated = changed - inserted
        stats = UpsertStats(inserted=inserted, updated=updated, skipped_stale=matched - updated)
        logger.info(
            "Upsert: %s inserted, %s updated, %s stale rows skipped",
            f"{stats.inserted:,}",
            f"{stats.updated:,}",
            f"{stats.skipped_stale:,}",
        )
        return stats

    def save_quarantine(self, df: pd.DataFrame, replace: bool) -> int:
        """Store rejected rows for review. ``replace`` mirrors a full refresh; otherwise append."""
        rows = _records(df, QUARANTINE_COLUMNS)
        placeholders = ", ".join("?" for _ in QUARANTINE_COLUMNS)
        sql = (
            f"INSERT INTO {QUARANTINE_TABLE} ({', '.join(QUARANTINE_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        with self._transaction() as conn:
            if replace:
                conn.execute(f"DELETE FROM {QUARANTINE_TABLE}")
            conn.executemany(sql, rows)
        return len(rows)

    def summary(self) -> LoadSummary:
        with closing(sqlite3.connect(self.db_path)) as conn:
            (total,) = conn.execute(f"SELECT COUNT(*) FROM {TARGET_TABLE}").fetchone()
            by_dc = dict(
                conn.execute(
                    f"SELECT distribution_center, COUNT(*) FROM {TARGET_TABLE} "
                    "GROUP BY 1 ORDER BY 1"
                )
            )
            by_source = dict(
                conn.execute(f"SELECT source, COUNT(*) FROM {TARGET_TABLE} GROUP BY 1 ORDER BY 1")
            )
            (dups,) = conn.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM {TARGET_TABLE} "
                "GROUP BY id, distribution_center HAVING COUNT(*) > 1)"
            ).fetchone()
        return LoadSummary(total=total, by_dc=by_dc, by_source=by_source, duplicate_keys=dups)
