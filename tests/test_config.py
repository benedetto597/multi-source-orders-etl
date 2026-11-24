from pathlib import Path

import pytest

from orders_etl.config import Settings


def test_defaults_when_env_empty():
    s = Settings.from_env({})
    assert s.source_db_url == "sqlite:///data/source/legacy_source.db"
    assert s.csv_dir == Path("data/csv")
    assert s.target_db_path == Path("data/target/warehouse.db")
    assert s.reports_dir == Path("reports")
    assert s.mode == "full"
    assert s.overlap_days == 30
    assert s.state_path == Path("data/target/etl_state.json")


def test_env_overrides():
    s = Settings.from_env(
        {
            "SOURCE_DB_URL": "sqlite:///x.db",
            "CSV_DIR": "in/csv",
            "TARGET_DB_PATH": "out/w.db",
            "REPORTS_DIR": "out/reports",
            "ETL_MODE": "incremental",
            "INCREMENTAL_OVERLAP_DAYS": "7",
            "ETL_STATE_PATH": "out/state.json",
        }
    )
    assert s.source_db_url == "sqlite:///x.db"
    assert s.csv_dir == Path("in/csv")
    assert s.target_db_path == Path("out/w.db")
    assert s.reports_dir == Path("out/reports")
    assert s.mode == "incremental"
    assert s.overlap_days == 7
    assert s.state_path == Path("out/state.json")


def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="ETL_MODE"):
        Settings.from_env({"ETL_MODE": "weekly"})
