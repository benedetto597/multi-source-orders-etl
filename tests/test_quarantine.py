import sqlite3
from contextlib import closing
from datetime import datetime

import pandas as pd

from orders_etl.load import SqliteLoader
from orders_etl.quarantine import split_invalid
from orders_etl.transform import add_load_metadata, normalize_schema


def _frame(rows):
    df = pd.DataFrame(rows, columns=["id", "distribution_center", "status"])
    df["source"] = "csv"
    df["created_at"] = "2024-01-01 00:00:00"
    return add_load_metadata(normalize_schema(df), datetime(2026, 1, 1))


def test_split_invalid_separates_missing_id_and_unknown_dc():
    df = _frame(
        [
            ("1", "dc_1", "Closed"),
            ("", "dc_1", "Closed"),
            (None, "dc_2", "Closed"),
            ("4", "unknown", "Closed"),
            ("5", "dc_2", "Closed"),
        ]
    )
    valid, rejected = split_invalid(df)
    assert valid["id"].tolist() == ["1", "5"]
    assert rejected["quarantine_reason"].tolist() == [
        "missing id",
        "missing id",
        "unknown distribution center",
    ]
    assert "quarantine_reason" not in valid.columns


def test_missing_id_takes_precedence_over_unknown_dc():
    _, rejected = split_invalid(_frame([(None, "unknown", "Closed")]))
    assert rejected["quarantine_reason"].tolist() == ["missing id"]


def test_split_invalid_with_nothing_to_reject():
    valid, rejected = split_invalid(_frame([("1", "dc_1", "Closed")]))
    assert len(valid) == 1
    assert rejected.empty
    assert "quarantine_reason" in rejected.columns


def _quarantine_rows(db):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(
            "SELECT id, distribution_center, quarantine_reason FROM quarantined_purchase_orders "
            "ORDER BY rowid"
        ).fetchall()


def test_save_quarantine_replace_and_append(tmp_path):
    loader = SqliteLoader(tmp_path / "w.db")
    loader.create_table()
    _, rejected = split_invalid(_frame([(None, "dc_1", "Closed"), ("4", "x", "Closed")]))

    assert loader.save_quarantine(rejected, replace=True) == 2
    assert loader.save_quarantine(rejected.iloc[:1], replace=False) == 1
    assert _quarantine_rows(loader.db_path) == [
        (None, "dc_1", "missing id"),
        ("4", "x", "unknown distribution center"),
        (None, "dc_1", "missing id"),
    ]

    loader.save_quarantine(rejected.iloc[1:], replace=True)
    assert _quarantine_rows(loader.db_path) == [("4", "x", "unknown distribution center")]
