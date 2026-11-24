"""Single source of truth for source/target table names and the target DDL."""

from __future__ import annotations

TARGET_TABLE = "consolidated_purchase_orders"

DISTRIBUTION_CENTERS: tuple[str, ...] = ("dc_1", "dc_2")

SOURCE_TABLES: dict[str, str] = {
    "dc_1": "purchase_orders_dc_1",
    "dc_2": "purchase_orders_dc_2",
}

VALID_SOURCES: tuple[str, ...] = ("sql_dc_1", "sql_dc_2", "csv")

VALID_STATUSES: tuple[str, ...] = (
    "Closed",
    "In progress",
    "Cancelled",
    "Confirmed",
    "Shipped",
    "Invoiced",
    "Partially received",
)

# Columns shared by every source (CSVs add ``update_month``).
SOURCE_COLUMNS: tuple[str, ...] = (
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
)

TARGET_COLUMNS: tuple[str, ...] = (
    "id",
    "distribution_center",
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
    "source",
    "loaded_at",
    "modified_at",
)

TIMESTAMP_COLUMNS: tuple[str, ...] = ("created_at", "updated_at", "loaded_at", "modified_at")

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
    id                  TEXT NOT NULL,
    distribution_center TEXT NOT NULL,
    order_code          TEXT,
    product_code        INTEGER,
    status              TEXT,
    received_quantity   INTEGER,
    requested_quantity  INTEGER,
    total               REAL,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    supplier_code       TEXT,
    update_month        TEXT,
    source              TEXT,
    loaded_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, distribution_center)
);
"""

INDEXES_SQL: tuple[str, ...] = (
    f"CREATE INDEX IF NOT EXISTS idx_dc ON {TARGET_TABLE}(distribution_center);",
    f"CREATE INDEX IF NOT EXISTS idx_created_at ON {TARGET_TABLE}(created_at);",
    f"CREATE INDEX IF NOT EXISTS idx_updated_at ON {TARGET_TABLE}(updated_at);",
    f"CREATE INDEX IF NOT EXISTS idx_status ON {TARGET_TABLE}(status);",
    f"CREATE INDEX IF NOT EXISTS idx_order_code ON {TARGET_TABLE}(order_code);",
)

# Rows that cannot be loaded (no business key) are set aside here for review instead of
# aborting the run. No primary key: the same bad row may be reported by several runs.
QUARANTINE_TABLE = "quarantined_purchase_orders"
QUARANTINE_COLUMNS: tuple[str, ...] = (*TARGET_COLUMNS, "quarantine_reason")

CREATE_QUARANTINE_SQL = f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
    id                  TEXT,
    distribution_center TEXT,
    order_code          TEXT,
    product_code        INTEGER,
    status              TEXT,
    received_quantity   INTEGER,
    requested_quantity  INTEGER,
    total               REAL,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    supplier_code       TEXT,
    update_month        TEXT,
    source              TEXT,
    loaded_at           TIMESTAMP,
    modified_at         TIMESTAMP,
    quarantine_reason   TEXT NOT NULL
);
"""
