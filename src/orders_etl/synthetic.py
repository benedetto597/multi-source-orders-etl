"""Deterministic synthetic data that reproduces the shape of the original challenge.

Two distribution centers (``dc_1``, ``dc_2``) expose the same purchase-order entity in a
"legacy" SQL database, but with inconsistent column types (schema drift). Monthly CSV drops
for March-December 2024 re-deliver some of those orders with later updates, so the same
``(id, distribution_center)`` appears in several sources and only the latest must survive.
"""

from __future__ import annotations

import csv
import random
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from orders_etl.schema import DISTRIBUTION_CENTERS, SOURCE_TABLES

_STATUSES = (
    "Closed",
    "Cancelled",
    "In progress",
    "Confirmed",
    "Shipped",
    "Invoiced",
    "Partially received",
)
_STATUS_WEIGHTS = (86.0, 11.0, 1.5, 0.5, 0.4, 0.3, 0.3)
_CSV_MONTHS = tuple(f"2024{m:02d}" for m in range(3, 13))
_TS = "%Y-%m-%d %H:%M:%S"

# dc_1 stores most columns as text/float; dc_2 uses "proper" types.
_DDL = {
    "dc_1": """
        CREATE TABLE purchase_orders_dc_1 (
            id INTEGER NOT NULL, order_code TEXT, product_code REAL, status TEXT,
            received_quantity INTEGER, requested_quantity TEXT, total REAL,
            created_at TEXT, updated_at TEXT, supplier_code TEXT)""",
    "dc_2": """
        CREATE TABLE purchase_orders_dc_2 (
            id TEXT NOT NULL, order_code INTEGER, product_code INTEGER NOT NULL,
            status TEXT NOT NULL, received_quantity INTEGER NOT NULL,
            requested_quantity INTEGER NOT NULL, total REAL NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT, supplier_code TEXT NOT NULL)""",
}
_CSV_HEADER = (
    "id",
    "order_code",
    "product_code",
    "status",
    "received_quantity",
    "requested_quantity",
    "total",
    "created_at",
    "updated_at",
    "supplier_code",
    "update_month",
)


@dataclass
class SyntheticSummary:
    sql_rows: dict[str, int] = field(default_factory=dict)
    csv_rows: dict[str, int] = field(default_factory=dict)
    csv_files: int = 0


def _random_ts(rng: random.Random, start: datetime, end: datetime) -> datetime:
    return start + timedelta(seconds=rng.randrange(int((end - start).total_seconds())))


def _order_values(rng: random.Random) -> dict:
    status = rng.choices(_STATUSES, weights=_STATUS_WEIGHTS)[0]
    requested = rng.randint(1, 300)
    if status in ("In progress", "Cancelled") and rng.random() < 0.5:
        received = 0
    elif rng.random() < 0.03:
        received = requested + rng.randint(1, 20)  # over-delivery: flagged by validation
    else:
        received = requested
    total = round(received * rng.uniform(1, 2000), 2)
    return {
        "status": status,
        "requested_quantity": requested,
        "received_quantity": received,
        "total": total,
        "product_code": rng.randint(4_000_000, 4_020_000),
        "supplier_code": f"Supplier {rng.randint(1, 80)}",
    }


def _write_sql(conn: sqlite3.Connection, dc: str, rows: list[dict]) -> None:
    conn.execute(_DDL[dc])
    out = []
    for r in rows:
        if dc == "dc_1":
            out.append(
                (
                    int(r["id"]),
                    f"{r['order_seq']}.0",
                    float(r["product_code"]),
                    r["status"],
                    r["received_quantity"],
                    str(r["requested_quantity"]),
                    r["total"],
                    r["created_at"],
                    r["updated_at"],
                    r["supplier_code"],
                )
            )
        else:
            out.append(
                (
                    r["id"],
                    r["order_seq"],
                    r["product_code"],
                    r["status"],
                    r["received_quantity"],
                    r["requested_quantity"],
                    r["total"],
                    r["created_at"],
                    r["updated_at"],
                    r["supplier_code"],
                )
            )
    conn.executemany(f"INSERT INTO {SOURCE_TABLES[dc]} VALUES (?,?,?,?,?,?,?,?,?,?)", out)


def generate(
    source_db: Path, csv_dir: Path, orders_per_dc: int = 3000, seed: int = 42
) -> SyntheticSummary:
    """Create (or overwrite) the SQLite source database and the monthly CSV files."""
    rng = random.Random(seed)
    source_db, csv_dir = Path(source_db), Path(csv_dir)
    source_db.parent.mkdir(parents=True, exist_ok=True)
    source_db.unlink(missing_ok=True)
    if csv_dir.exists():
        shutil.rmtree(csv_dir)

    summary = SyntheticSummary()
    sql_start, sql_end = datetime(2023, 1, 2), datetime(2024, 2, 29, 23, 59, 59)
    csv_rows_per_month = max(1, orders_per_dc // 13)

    with closing(sqlite3.connect(source_db)) as conn, conn:
        for dc_index, dc in enumerate(DISTRIBUTION_CENTERS, start=1):
            # Ids overlap across DCs on purpose: (id, dc) is the business key.
            ids = rng.sample(range(10_000, 10_000 + orders_per_dc * 20), orders_per_dc)
            sql_rows = []
            for i, id_ in enumerate(ids):
                created = _random_ts(rng, sql_start, sql_end)
                updated = created + timedelta(days=rng.randint(0, 90), seconds=rng.randrange(86400))
                row = {"id": str(id_), "order_seq": 7000 + i, **_order_values(rng)}
                row["created_at"] = created.strftime(_TS)
                row["updated_at"] = updated.strftime(_TS)
                if dc == "dc_2" and rng.random() < 0.05:
                    row["updated_at"] = None
                if dc == "dc_1" and rng.random() < 0.005:
                    row["created_at"] = "N/A"
                sql_rows.append(row)
            _write_sql(conn, dc, sql_rows)
            summary.sql_rows[dc] = len(sql_rows)

            dc_dir = csv_dir / dc
            dc_dir.mkdir(parents=True, exist_ok=True)
            next_id = 10_000 + orders_per_dc * 20
            next_seq = 10_000_000 + orders_per_dc
            total_csv = 0
            for month in _CSV_MONTHS:
                year, mon = int(month[:4]), int(month[4:])
                m_start = datetime(year, mon, 1)
                m_end = datetime(year + (mon == 12), mon % 12 + 1, 1) - timedelta(seconds=1)
                rows = []
                for _ in range(csv_rows_per_month):
                    if rng.random() < 0.30:  # re-delivery of an SQL order with a newer state
                        base = rng.choice(sql_rows)
                        id_, seq = base["id"], 10_000_000 + base["order_seq"]
                    else:
                        id_, seq = str(next_id), next_seq
                        next_id += 1
                        next_seq += 1
                    updated = _random_ts(rng, m_start, m_end)
                    created = updated - timedelta(
                        days=rng.randint(0, 20), seconds=rng.randrange(86400)
                    )
                    v = _order_values(rng)
                    order_code = "" if rng.random() < 0.02 else f"{dc_index}{seq}.0"
                    updated_txt = "N/A" if rng.random() < 0.01 else updated.strftime(_TS)
                    update_month = (updated + timedelta(days=rng.randint(0, 60))).strftime("%Y%m")
                    rows.append(
                        (
                            id_,
                            order_code,
                            f"{float(v['product_code'])}",
                            v["status"],
                            v["received_quantity"],
                            v["requested_quantity"],
                            v["total"],
                            created.strftime(_TS),
                            updated_txt,
                            v["supplier_code"],
                            update_month,
                        )
                    )
                with (dc_dir / f"orders_{month}.csv").open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, lineterminator="\n")
                    writer.writerow(_CSV_HEADER)
                    writer.writerows(rows)
                total_csv += len(rows)
                summary.csv_files += 1
            summary.csv_rows[dc] = total_csv
    return summary
