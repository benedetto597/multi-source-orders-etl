import sqlite3
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytest

from orders_etl.load import SqliteLoader
from orders_etl.transform import add_load_metadata, normalize_schema
from orders_etl.validate import DataValidator, Expectations


def _frame(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "distribution_center",
            "status",
            "received_quantity",
            "requested_quantity",
            "created_at",
        ],
    )
    df["source"] = "csv"
    return add_load_metadata(normalize_schema(df), datetime(2026, 1, 1))


GOOD = [
    ("1", "dc_1", "Closed", 5, 5, "2024-01-01 00:00:00"),
    ("2", "dc_2", "Cancelled", 0, 3, "2024-06-01 00:00:00"),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "w.db"
    loader = SqliteLoader(path)
    loader.create_table()
    loader.replace_all(_frame(GOOD))
    return path


def _status(report, name):
    return next(c.status for c in report.checks if c.name == name)


def test_valid_db_passes(db):
    report = DataValidator(db).run()
    assert report.ok
    assert len(report.checks) == 9
    assert {c.status for c in report.checks} == {"PASS"}


def test_missing_table_fails_fast(tmp_path):
    report = DataValidator(tmp_path / "empty.db").run()
    assert not report.ok
    assert [(c.name, c.status) for c in report.checks] == [("Table exists", "FAIL")]


def test_row_count_outside_expected_range_warns(db):
    report = DataValidator(db, Expectations(min_rows=10)).run()
    assert _status(report, "Row count") == "WARN"
    assert report.ok


def test_duplicates_fail(tmp_path):
    path = tmp_path / "dups.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE consolidated_purchase_orders (id TEXT, distribution_center TEXT, "
            "source TEXT, status TEXT, received_quantity INT, requested_quantity INT, "
            "total REAL, created_at TEXT)"
        )
        conn.executemany(
            "INSERT INTO consolidated_purchase_orders VALUES (?,?,?,?,?,?,?,?)",
            [("1", "dc_1", "csv", "Closed", 1, 1, 1.0, "2024-01-01")] * 2
            + [("2", "dc_2", "csv", "Closed", 1, 1, 1.0, "2024-01-01")],
        )
    report = DataValidator(path).run()
    assert _status(report, "Duplicate keys") == "FAIL"
    assert not report.ok


def test_unknown_status_warns(tmp_path):
    path = tmp_path / "w.db"
    loader = SqliteLoader(path)
    loader.create_table()
    loader.replace_all(_frame([*GOOD, ("3", "dc_1", "Lost", 1, 1, "2024-01-01 00:00:00")]))
    report = DataValidator(path).run()
    assert _status(report, "Valid statuses") == "WARN"
    assert report.ok


def test_negative_quantity_fails(tmp_path):
    path = tmp_path / "w.db"
    loader = SqliteLoader(path)
    loader.create_table()
    loader.replace_all(_frame([*GOOD, ("3", "dc_1", "Closed", -1, 1, "2024-01-01 00:00:00")]))
    report = DataValidator(path).run()
    assert _status(report, "Numeric consistency") == "FAIL"


def test_over_delivery_only_warns(tmp_path):
    path = tmp_path / "w.db"
    loader = SqliteLoader(path)
    loader.create_table()
    loader.replace_all(_frame([*GOOD, ("3", "dc_1", "Closed", 9, 1, "2024-01-01 00:00:00")]))
    report = DataValidator(path).run()
    assert _status(report, "Numeric consistency") == "WARN"


def test_dates_out_of_range_warn(db):
    report = DataValidator(db, Expectations(date_min="2024-03-01")).run()
    assert _status(report, "Date range") == "WARN"


def test_render_contains_summary(db):
    text = DataValidator(db).run().render()
    assert "VALIDATION REPORT" in text
    assert "Passed: 9" in text
    assert "RESULT: PASSED" in text


def test_quarantined_rows_warn(db):
    from orders_etl.quarantine import split_invalid

    loader = SqliteLoader(db)
    _, rejected = split_invalid(_frame([(None, "dc_1", "Closed", 1, 1, "2024-01-01 00:00:00")]))
    loader.save_quarantine(rejected, replace=True)
    report = DataValidator(db).run()
    assert _status(report, "Quarantined rows") == "WARN"
    assert "missing id: 1" in next(c.detail for c in report.checks if c.name == "Quarantined rows")
    assert report.ok
