from datetime import datetime

import pandas as pd

from orders_etl.transform import add_load_metadata, normalize_schema


def _raw(**overrides):
    row = {
        "id": 11944,
        "order_code": "7255.0",
        "product_code": 15648.0,
        "status": "Closed",
        "received_quantity": 71,
        "requested_quantity": "71",
        "total": 12036.91,
        "created_at": "2023-06-09 15:14:26",
        "updated_at": "2023-08-17 01:04:48",
        "supplier_code": "Supplier 5",
        "distribution_center": "dc_1",
        "source": "sql_dc_1",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_id_and_codes_become_clean_strings():
    out = normalize_schema(_raw(id=11944.0))
    assert out.loc[0, "id"] == "11944"
    assert out.loc[0, "order_code"] == "7255"


def test_order_code_float_string_normalized():
    out = normalize_schema(_raw(order_code="110012913.0"))
    assert out.loc[0, "order_code"] == "110012913"


def test_empty_order_code_becomes_none():
    out = normalize_schema(pd.concat([_raw(order_code=""), _raw(order_code=None)]))
    assert out["order_code"].isna().all()
    assert len(out) == 2


def test_text_quantity_parsed():
    out = normalize_schema(_raw(requested_quantity="80", product_code="4007260.0"))
    assert out.loc[0, "requested_quantity"] == 80
    assert str(out["requested_quantity"].dtype) == "Int64"
    assert out.loc[0, "product_code"] == 4007260


def test_unparseable_date_becomes_nat_and_row_kept():
    out = normalize_schema(_raw(updated_at="N/A", created_at="2024-03-19T12:29:57"))
    assert len(out) == 1
    assert pd.isna(out.loc[0, "updated_at"])
    assert out.loc[0, "created_at"] == pd.Timestamp("2024-03-19 12:29:57")


def test_update_month_created_when_missing_and_cleaned_when_present():
    assert normalize_schema(_raw())["update_month"].isna().all()
    assert normalize_schema(_raw(update_month="202403.0")).loc[0, "update_month"] == "202403"


def test_normalize_does_not_mutate_input():
    raw = _raw()
    before = raw.copy()
    normalize_schema(raw)
    pd.testing.assert_frame_equal(raw, before)


def test_add_load_metadata_sets_both_timestamps():
    ts = datetime(2026, 1, 1, 12, 0)
    out = add_load_metadata(normalize_schema(_raw()), ts)
    assert out.loc[0, "loaded_at"] == ts
    assert out.loc[0, "modified_at"] == ts
