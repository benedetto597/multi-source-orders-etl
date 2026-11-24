"""Normalize the heterogeneous source schemas into the target types."""

from __future__ import annotations

import logging
import math
from datetime import datetime

import pandas as pd

from orders_etl.schema import SOURCE_COLUMNS

logger = logging.getLogger(__name__)


def _to_code(value: object) -> str | None:
    """Integer-like codes arrive as int, float, "7255.0" or text; return clean text or None."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def _to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def _to_timestamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="ISO8601")


def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with every column cast to its target type.

    Unparseable values become null instead of failing the run; the row is kept so the
    validation step can report on it.
    """
    out = df.copy()
    for col in (*SOURCE_COLUMNS, "update_month"):
        if col not in out.columns:
            out[col] = None
    for col in ("id", "order_code", "update_month"):
        out[col] = out[col].map(_to_code).astype("object")
    for col in ("product_code", "received_quantity", "requested_quantity"):
        out[col] = _to_int(out[col])
    out["total"] = pd.to_numeric(out["total"], errors="coerce").astype("float64")
    for col in ("created_at", "updated_at"):
        out[col] = _to_timestamp(out[col])
    for col in ("status", "supplier_code"):
        out[col] = out[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    logger.info("Normalized %s rows", f"{len(out):,}")
    return out


def add_load_metadata(df: pd.DataFrame, loaded_at: datetime) -> pd.DataFrame:
    out = df.copy()
    out["loaded_at"] = loaded_at
    out["modified_at"] = loaded_at
    return out
