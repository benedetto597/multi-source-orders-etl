import csv
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from orders_etl.config import Settings
from orders_etl.pipeline import run_pipeline
from orders_etl.state import WatermarkStore
from orders_etl.synthetic import generate

NOW = datetime(2026, 1, 10, 9, 0, 0)


@pytest.fixture
def settings(tmp_path) -> Settings:
    source = tmp_path / "source" / "legacy.db"
    generate(source, tmp_path / "csv", orders_per_dc=300, seed=11)
    return Settings.from_env(
        {
            "SOURCE_DB_URL": f"sqlite:///{source.as_posix()}",
            "CSV_DIR": str(tmp_path / "csv"),
            "TARGET_DB_PATH": str(tmp_path / "target" / "warehouse.db"),
            "REPORTS_DIR": str(tmp_path / "reports"),
            "ETL_STATE_PATH": str(tmp_path / "target" / "state.json"),
        }
    )


def _target(settings, sql):
    with closing(sqlite3.connect(settings.target_db_path)) as conn:
        return conn.execute(sql).fetchall()


def _unique_source_keys(settings) -> int:
    src = settings.source_db_url.removeprefix("sqlite:///")
    keys = set()
    with closing(sqlite3.connect(src)) as conn:
        for dc in ("dc_1", "dc_2"):
            keys |= {(str(r[0]), dc) for r in conn.execute(f"SELECT id FROM purchase_orders_{dc}")}
    for f in Path(settings.csv_dir).glob("*/orders_*.csv"):
        keys |= {(i, f.parent.name) for i in pd.read_csv(f, dtype=str)["id"].dropna()}
    return len(keys)


def test_full_run_end_to_end(settings):
    result = run_pipeline(settings, now=NOW)
    assert result.mode == "full"
    assert result.load.duplicate_keys == 0
    assert result.load.total == result.dedup.final == _unique_source_keys(settings)
    assert result.dedup.removed > 0
    assert set(result.load.by_dc) == {"dc_1", "dc_2"}
    assert set(result.load.by_source) == {"sql_dc_1", "sql_dc_2", "csv"}
    assert WatermarkStore(settings.state_path).get() is not None


def _csv_rows_without_id(settings) -> int:
    return sum(
        int(pd.read_csv(f, dtype=str)["id"].isna().sum())
        for f in Path(settings.csv_dir).glob("*/orders_*.csv")
    )


def test_full_run_quarantines_rows_without_id(settings):
    expected = _csv_rows_without_id(settings)
    assert expected > 0  # the synthetic data contains some
    result = run_pipeline(settings, now=NOW)
    assert result.quarantined == expected
    reasons = _target(
        settings, "SELECT DISTINCT quarantine_reason FROM quarantined_purchase_orders"
    )
    assert reasons == [("missing id",)]


def test_full_run_twice_same_count(settings):
    first = run_pipeline(settings, now=NOW)
    second = run_pipeline(settings, now=NOW)
    assert second.load.total == first.load.total
    assert second.load.duplicate_keys == 0
    (n,) = _target(settings, "SELECT COUNT(*) FROM quarantined_purchase_orders")[0]
    assert n == first.quarantined  # full refresh replaces the quarantine too


def test_runs_without_csv_dir(settings, tmp_path):
    no_csv = replace(settings, csv_dir=tmp_path / "missing")
    result = run_pipeline(no_csv, now=NOW)
    assert set(result.load.by_source) == {"sql_dc_1", "sql_dc_2"}
    assert result.load.total > 0


def test_incremental_second_run_upserts(settings):
    full = run_pipeline(settings, now=NOW)
    csv_file = Path(settings.csv_dir) / "dc_1" / "orders_202412.csv"
    rows = list(csv.DictReader(csv_file.open(encoding="utf-8")))
    target_id = rows[0]["id"]
    rows[0]["updated_at"] = "2025-01-05 10:00:00"
    rows[0]["status"] = "Invoiced"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    inc = run_pipeline(replace(settings, mode="incremental"), now=NOW)

    assert inc.mode == "incremental"
    assert inc.extracted < full.extracted  # only the overlap window was read
    assert inc.upsert is not None and inc.upsert.updated >= 1
    assert inc.load.total == full.load.total
    status = _target(
        settings,
        "SELECT status FROM consolidated_purchase_orders "
        f"WHERE id = '{target_id}' AND distribution_center = 'dc_1'",
    )
    assert status == [("Invoiced",)]


def test_incremental_without_watermark_reads_everything(settings):
    result = run_pipeline(replace(settings, mode="incremental"), now=NOW)
    assert result.upsert is not None
    assert result.upsert.inserted == result.load.total
