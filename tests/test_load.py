import sqlite3
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytest

from orders_etl.load import LoadSummary, SqliteLoader, UpsertStats
from orders_etl.transform import add_load_metadata, normalize_schema

T0 = datetime(2026, 1, 1, 8, 0, 0)
T1 = datetime(2026, 1, 2, 8, 0, 0)


def _orders(rows, loaded_at=T0):
    df = pd.DataFrame(rows, columns=["id", "distribution_center", "status", "source"])
    df["created_at"] = "2024-01-01 10:00:00"
    df["updated_at"] = None
    df["received_quantity"] = 5
    df["requested_quantity"] = "5"
    return add_load_metadata(normalize_schema(df), loaded_at)


def _query(db, sql):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(sql).fetchall()


@pytest.fixture
def loader(tmp_path):
    ld = SqliteLoader(tmp_path / "target" / "warehouse.db")
    ld.create_table()
    return ld


def test_replace_all_loads_rows(loader):
    n = loader.replace_all(
        _orders([("1", "dc_1", "Closed", "csv"), ("2", "dc_2", "Closed", "csv")])
    )
    assert n == 2
    assert _query(loader.db_path, "SELECT COUNT(*) FROM consolidated_purchase_orders") == [(2,)]


def test_replace_all_is_idempotent(loader):
    df = _orders([("1", "dc_1", "Closed", "csv"), ("2", "dc_2", "Closed", "csv")])
    loader.replace_all(df)
    loader.replace_all(df)
    assert loader.summary().total == 2


def test_replace_all_rolls_back_on_error(loader):
    loader.replace_all(_orders([("1", "dc_1", "Closed", "csv"), ("2", "dc_1", "Closed", "csv")]))
    bad = _orders([("3", "dc_1", "Closed", "csv"), (None, "dc_1", "Closed", "csv")])
    with pytest.raises(sqlite3.IntegrityError):
        loader.replace_all(bad)
    ids = _query(loader.db_path, "SELECT id FROM consolidated_purchase_orders ORDER BY id")
    assert ids == [("1",), ("2",)]


def test_timestamps_stored_as_text_and_na_as_null(loader):
    loader.replace_all(_orders([("1", "dc_1", "Closed", "csv")]))
    row = _query(
        loader.db_path,
        "SELECT created_at, updated_at, loaded_at, order_code FROM consolidated_purchase_orders",
    )
    assert row == [("2024-01-01 10:00:00", None, "2026-01-01 08:00:00", None)]


def test_upsert_counts_inserts_and_updates(loader):
    loader.replace_all(_orders([("1", "dc_1", "In progress", "sql_dc_1")]))
    stats = loader.upsert(
        _orders([("1", "dc_1", "Closed", "csv"), ("9", "dc_2", "Closed", "csv")], loaded_at=T1)
    )
    assert stats == UpsertStats(inserted=1, updated=1)
    row = _query(
        loader.db_path,
        "SELECT status, source, loaded_at, modified_at FROM consolidated_purchase_orders "
        "WHERE id = '1'",
    )
    # loaded_at keeps the first load; modified_at tracks the update.
    assert row == [("Closed", "csv", "2026-01-01 08:00:00", "2026-01-02 08:00:00")]


def test_summary_counts(loader):
    loader.replace_all(
        _orders(
            [
                ("1", "dc_1", "Closed", "sql_dc_1"),
                ("2", "dc_1", "Closed", "csv"),
                ("1", "dc_2", "Closed", "csv"),
            ]
        )
    )
    assert loader.summary() == LoadSummary(
        total=3,
        by_dc={"dc_1": 2, "dc_2": 1},
        by_source={"csv": 2, "sql_dc_1": 1},
        duplicate_keys=0,
    )
