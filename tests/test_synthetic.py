import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from orders_etl.synthetic import generate


def _fingerprint(source_db: Path, csv_dir: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(csv_dir.rglob("*.csv")):
        h.update(f.relative_to(csv_dir).as_posix().encode())
        h.update(f.read_bytes())
    with sqlite3.connect(source_db) as conn:
        for table in ("purchase_orders_dc_1", "purchase_orders_dc_2"):
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid"):
                h.update(repr(row).encode())
    return h.hexdigest()


def test_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a / "src.db", a / "csv", orders_per_dc=200, seed=42)
    generate(b / "src.db", b / "csv", orders_per_dc=200, seed=42)
    assert _fingerprint(a / "src.db", a / "csv") == _fingerprint(b / "src.db", b / "csv")


def test_regenerating_overwrites_previous_output(tmp_path):
    generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=200, seed=1)
    summary = generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=100, seed=1)
    with sqlite3.connect(tmp_path / "src.db") as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM purchase_orders_dc_1").fetchone()
    assert n == summary.sql_rows["dc_1"] == 100


def test_creates_ten_csvs_per_dc(tmp_path):
    summary = generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=200)
    for dc in ("dc_1", "dc_2"):
        files = sorted(p.name for p in (tmp_path / "csv" / dc).glob("orders_*.csv"))
        assert files == [f"orders_2024{m:02d}.csv" for m in range(3, 13)]
    assert summary.csv_files == 20
    assert summary.sql_rows == {"dc_1": 200, "dc_2": 200}


def test_dc1_has_text_typed_columns(tmp_path):
    generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=200)
    with sqlite3.connect(tmp_path / "src.db") as conn:
        dc1 = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(purchase_orders_dc_1)")}
        dc2 = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(purchase_orders_dc_2)")}
    assert dc1["id"] == "INTEGER" and dc2["id"] == "TEXT"
    assert dc1["order_code"] == "TEXT" and dc2["order_code"] == "INTEGER"
    assert dc1["requested_quantity"] == "TEXT" and dc2["requested_quantity"] == "INTEGER"
    assert dc1["product_code"] == "REAL"


def test_csv_reuses_sql_ids(tmp_path):
    generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=300)
    with sqlite3.connect(tmp_path / "src.db") as conn:
        sql_ids = {str(r[0]) for r in conn.execute("SELECT id FROM purchase_orders_dc_1")}
    csv_ids = set(
        pd.concat(pd.read_csv(f, dtype=str) for f in (tmp_path / "csv" / "dc_1").glob("*.csv"))[
            "id"
        ]
    )
    assert len(sql_ids & csv_ids) > 0


def test_contains_unparseable_dates_and_missing_updates(tmp_path):
    generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=500)
    csv = pd.concat(
        pd.read_csv(f, dtype=str, keep_default_na=False) for f in (tmp_path / "csv").rglob("*.csv")
    )
    assert (csv["updated_at"] == "N/A").any()
    assert (csv["order_code"] == "").any()
    with sqlite3.connect(tmp_path / "src.db") as conn:
        (nulls,) = conn.execute(
            "SELECT COUNT(*) FROM purchase_orders_dc_2 WHERE updated_at IS NULL"
        ).fetchone()
    assert nulls > 0


def test_some_csv_rows_have_no_id(tmp_path):
    generate(tmp_path / "src.db", tmp_path / "csv", orders_per_dc=1000)
    csv = pd.concat(pd.read_csv(f, dtype=str) for f in (tmp_path / "csv").rglob("*.csv"))
    assert 0 < csv["id"].isna().sum() < len(csv) * 0.01
