import pandas as pd

from orders_etl.dedup import DedupStats, remove_duplicates


def _frame(rows):
    df = pd.DataFrame(
        rows, columns=["id", "distribution_center", "created_at", "updated_at", "tag"]
    )
    for col in ("created_at", "updated_at"):
        df[col] = pd.to_datetime(df[col])
    return df


def test_dedup_keeps_latest_updated_at():
    df = _frame(
        [
            ("123", "dc_1", "2024-01-01", "2024-05-15", "may"),
            ("123", "dc_1", "2024-01-01", "2024-06-20", "june"),
            ("123", "dc_1", "2024-01-01", "2024-04-10", "april"),
        ]
    )
    out, _ = remove_duplicates(df)
    assert out["tag"].tolist() == ["june"]


def test_dedup_falls_back_to_created_at():
    df = _frame(
        [
            ("1", "dc_2", "2024-02-01", None, "newer-created"),
            ("1", "dc_2", "2024-01-01", "2024-01-15", "older-updated"),
        ]
    )
    out, _ = remove_duplicates(df)
    assert out["tag"].tolist() == ["newer-created"]


def test_dedup_nat_row_loses():
    df = _frame(
        [
            ("1", "dc_1", None, None, "undated"),
            ("1", "dc_1", "2023-01-01", None, "dated"),
        ]
    )
    out, _ = remove_duplicates(df)
    assert out["tag"].tolist() == ["dated"]


def test_dedup_tie_prefers_later_row():
    df = _frame(
        [
            ("1", "dc_1", "2024-01-01", "2024-02-01", "sql"),
            ("1", "dc_1", "2024-01-01", "2024-02-01", "csv"),
        ]
    )
    out, _ = remove_duplicates(df)
    assert out["tag"].tolist() == ["csv"]


def test_dedup_same_id_different_dc_not_duplicate():
    df = _frame(
        [
            ("1", "dc_1", "2024-01-01", None, "a"),
            ("1", "dc_2", "2024-01-01", None, "b"),
        ]
    )
    out, stats = remove_duplicates(df)
    assert len(out) == 2
    assert stats.removed == 0


def test_dedup_stats_and_no_helper_columns():
    df = _frame(
        [
            ("1", "dc_1", "2024-01-01", None, "a"),
            ("1", "dc_1", "2024-01-02", None, "b"),
            ("1", "dc_1", "2024-01-03", None, "c"),
            ("2", "dc_1", "2024-01-01", None, "d"),
        ]
    )
    out, stats = remove_duplicates(df)
    assert stats == DedupStats(initial=4, final=2, removed=2, rows_in_duplicate_groups=3)
    assert list(out.columns) == list(df.columns)
    assert list(out.index) == [0, 1]
