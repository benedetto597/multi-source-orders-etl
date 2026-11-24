"""End-to-end orchestration: extract -> normalize -> deduplicate -> load."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from orders_etl.config import Mode, Settings
from orders_etl.dedup import DedupStats, remove_duplicates
from orders_etl.extract import CsvExtractor, SqlSourceExtractor, months_since
from orders_etl.load import LoadSummary, SqliteLoader, UpsertStats
from orders_etl.quarantine import split_invalid
from orders_etl.state import WatermarkStore
from orders_etl.transform import add_load_metadata, normalize_schema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    mode: Mode
    extracted: int
    dedup: DedupStats
    load: LoadSummary
    upsert: UpsertStats | None
    seconds: float
    since: datetime | None = None
    quarantined: int = 0


def run_pipeline(settings: Settings, now: datetime | None = None) -> PipelineResult:
    """Run one ETL cycle.

    * ``full``: read everything and atomically replace the target table.
    * ``incremental``: read only rows changed since ``watermark - overlap_days`` (everything
      on the first run) and upsert them; older re-deliveries never overwrite newer rows.
    """
    started = time.perf_counter()
    now = now or datetime.now()
    store = WatermarkStore(settings.state_path)

    since: datetime | None = None
    months: set[str] | None = None
    if settings.mode == "incremental":
        watermark = store.get()
        if watermark is not None:
            since = watermark - timedelta(days=settings.overlap_days)
            months = months_since(since, until=now)
        logger.info("Incremental run, reading changes since %s", since or "the beginning")

    with SqlSourceExtractor(settings.source_db_url) as sql:
        sql_df = sql.extract_all(since=since)
    csv_df = CsvExtractor(settings.csv_dir).extract(months=months)
    raw = pd.concat([df for df in (sql_df, csv_df) if not df.empty], ignore_index=True)
    logger.info("Extracted %s rows in total", f"{len(raw):,}")

    clean = add_load_metadata(normalize_schema(raw), loaded_at=now)
    valid, rejected = split_invalid(clean)
    deduped, dedup_stats = remove_duplicates(valid)

    loader = SqliteLoader(settings.target_db_path)
    loader.create_table()
    upsert_stats: UpsertStats | None = None
    if settings.mode == "full":
        loader.replace_all(deduped)
    else:
        upsert_stats = loader.upsert(deduped)
    loader.save_quarantine(rejected, replace=settings.mode == "full")

    reference = deduped["updated_at"].fillna(deduped["created_at"]).max()
    if pd.notna(reference):
        previous = store.get()
        new_mark = reference.to_pydatetime()
        store.set(max(new_mark, previous) if previous else new_mark, rows=len(deduped))

    return PipelineResult(
        mode=settings.mode,
        extracted=len(raw),
        dedup=dedup_stats,
        load=loader.summary(),
        upsert=upsert_stats,
        seconds=round(time.perf_counter() - started, 2),
        since=since,
        quarantined=len(rejected),
    )
