"""Extractors for the legacy SQL source and the monthly CSV drops."""

from __future__ import annotations

import logging
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from orders_etl.schema import DISTRIBUTION_CENTERS, SOURCE_COLUMNS, SOURCE_TABLES

logger = logging.getLogger(__name__)

_EMPTY_COLUMNS = [*SOURCE_COLUMNS, "update_month", "distribution_center", "source"]


def infer_dc_from_order_code(value: object) -> str:
    """CSV order codes start with the distribution-center number ("110012913.0" -> dc_1)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "unknown"
    code = str(value).strip()
    if code[:1] == "1":
        return "dc_1"
    if code[:1] == "2":
        return "dc_2"
    return "unknown"


def months_since(since: datetime, until: datetime | None = None) -> set[str]:
    """All ``YYYYMM`` months from ``since`` through ``until`` (default: now), inclusive."""
    until = until or datetime.now()
    year, month = since.year, since.month
    months: set[str] = set()
    while (year, month) <= (until.year, until.month):
        months.add(f"{year}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


class SqlSourceExtractor:
    """Reads the per-DC tables from any SQLAlchemy-supported database."""

    def __init__(self, url: str):
        self.engine = create_engine(url)

    def __enter__(self) -> SqlSourceExtractor:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.engine.dispose()

    def extract_table(self, table: str, dc: str, since: datetime | None = None) -> pd.DataFrame:
        if SOURCE_TABLES.get(dc) != table:
            raise ValueError(f"Unknown source table {table!r} for distribution center {dc!r}")
        query = f"SELECT * FROM {table}"
        params: dict[str, object] = {}
        if since is not None:
            query += " WHERE COALESCE(updated_at, created_at) >= :since"
            # SQLite stores these timestamps as ISO text; other engines bind a real datetime.
            sqlite = self.engine.dialect.name == "sqlite"
            params["since"] = since.strftime("%Y-%m-%d %H:%M:%S") if sqlite else since
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params)
        df["distribution_center"] = dc
        df["source"] = f"sql_{dc}"
        logger.info(
            "Extracted %s rows from %s%s", f"{len(df):,}", table, " (incremental)" * bool(since)
        )
        return df

    def extract_all(self, since: datetime | None = None) -> pd.DataFrame:
        frames = [self.extract_table(SOURCE_TABLES[dc], dc, since) for dc in DISTRIBUTION_CENTERS]
        return pd.concat(frames, ignore_index=True)


class CsvExtractor:
    """Reads ``<csv_dir>/<dc>/orders_YYYYMM.csv`` files as text (typing happens in transform)."""

    def __init__(self, csv_dir: Path):
        self.csv_dir = Path(csv_dir)

    def _files(self, months: set[str] | None) -> list[Path]:
        if not self.csv_dir.is_dir():
            return []
        files = sorted(self.csv_dir.glob("*/orders_*.csv"))
        if months is not None:
            files = [f for f in files if f.stem.removeprefix("orders_")[:6] in months]
        return files

    def extract(self, months: set[str] | None = None) -> pd.DataFrame:
        files = self._files(months)
        if not files:
            logger.warning("No CSV files found in %s", self.csv_dir)
            return pd.DataFrame(columns=_EMPTY_COLUMNS)
        frames = []
        for f in files:
            df = pd.read_csv(f, dtype=str)
            folder = f.parent.name
            if folder in DISTRIBUTION_CENTERS:
                df["distribution_center"] = folder
            else:
                df["distribution_center"] = df["order_code"].map(infer_dc_from_order_code)
            df["source"] = "csv"
            frames.append(df)
            logger.info("Read %s rows from %s/%s", f"{len(df):,}", folder, f.name)
        out = pd.concat(frames, ignore_index=True)
        logger.info("Extracted %s CSV rows from %d files", f"{len(out):,}", len(files))
        return out
