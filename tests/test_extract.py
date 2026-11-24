import logging
from datetime import datetime

import pandas as pd
import pytest

from orders_etl.extract import (
    CsvExtractor,
    SqlSourceExtractor,
    infer_dc_from_order_code,
    months_since,
)
from orders_etl.synthetic import generate


@pytest.fixture
def synthetic(tmp_path):
    db, csv_dir = tmp_path / "src.db", tmp_path / "csv"
    summary = generate(db, csv_dir, orders_per_dc=200, seed=7)
    return f"sqlite:///{db.as_posix()}", csv_dir, summary


def test_sql_extract_adds_metadata(synthetic):
    url, _, summary = synthetic
    with SqlSourceExtractor(url) as ex:
        df = ex.extract_table("purchase_orders_dc_1", "dc_1")
    assert len(df) == summary.sql_rows["dc_1"]
    assert set(df["distribution_center"]) == {"dc_1"}
    assert set(df["source"]) == {"sql_dc_1"}


def test_sql_extract_all_concatenates_both_dcs(synthetic):
    url, _, summary = synthetic
    with SqlSourceExtractor(url) as ex:
        df = ex.extract_all()
    assert len(df) == sum(summary.sql_rows.values())
    assert set(df["distribution_center"]) == {"dc_1", "dc_2"}


def test_sql_extract_since_filters_rows(synthetic):
    url, _, _ = synthetic
    since = datetime(2024, 1, 1)
    with SqlSourceExtractor(url) as ex:
        full = ex.extract_table("purchase_orders_dc_2", "dc_2")
        recent = ex.extract_table("purchase_orders_dc_2", "dc_2", since=since)
    ref = pd.to_datetime(full["updated_at"].fillna(full["created_at"]))
    assert 0 < len(recent) < len(full)
    assert len(recent) == int((ref >= since).sum())


def test_sql_extract_rejects_unknown_table(synthetic):
    url, _, _ = synthetic
    with SqlSourceExtractor(url) as ex, pytest.raises(ValueError, match="Unknown source table"):
        ex.extract_table("sqlite_master; DROP TABLE x", "dc_1")


def test_csv_extract_detects_dc_from_folder(synthetic):
    _, csv_dir, summary = synthetic
    df = CsvExtractor(csv_dir).extract()
    assert len(df) == sum(summary.csv_rows.values())
    counts = df["distribution_center"].value_counts().to_dict()
    assert counts == summary.csv_rows
    assert set(df["source"]) == {"csv"}
    assert df["id"].map(type).eq(str).all()  # read as text, normalization happens later


def test_csv_extract_infers_dc_outside_dc_folders(tmp_path):
    folder = tmp_path / "csv" / "mixed"
    folder.mkdir(parents=True)
    (folder / "orders_202403.csv").write_text(
        "id,order_code,updated_at\n1,110012913.0,2024-03-01 00:00:00\n2,210008248.0,\n",
        encoding="utf-8",
    )
    df = CsvExtractor(tmp_path / "csv").extract()
    assert df.sort_values("id")["distribution_center"].tolist() == ["dc_1", "dc_2"]


def test_csv_month_filter(synthetic):
    _, csv_dir, _ = synthetic
    df = CsvExtractor(csv_dir).extract(months={"202411", "202412"})
    expected = sum(
        len(pd.read_csv(csv_dir / dc / f"orders_{m}.csv"))
        for dc in ("dc_1", "dc_2")
        for m in ("202411", "202412")
    )
    assert len(df) == expected


def test_csv_missing_dir_returns_empty_frame_and_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        df = CsvExtractor(tmp_path / "nope").extract()
    assert df.empty
    assert {"id", "distribution_center", "source"} <= set(df.columns)
    assert "No CSV files" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("110012913.0", "dc_1"),
        (210008248, "dc_2"),
        (210008248.0, "dc_2"),
        ("", "unknown"),
        (None, "unknown"),
        (float("nan"), "unknown"),
        ("ABC", "unknown"),
    ],
)
def test_infer_dc_from_order_code(value, expected):
    assert infer_dc_from_order_code(value) == expected


def test_months_since_spans_year_boundary():
    got = months_since(datetime(2024, 11, 15), until=datetime(2025, 2, 1))
    assert got == {"202411", "202412", "202501", "202502"}
