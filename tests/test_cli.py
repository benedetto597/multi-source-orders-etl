import sqlite3
from contextlib import closing

import pytest

from orders_etl.cli import main


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run the CLI from an empty folder with default (relative) settings."""
    monkeypatch.chdir(tmp_path)
    for var in ("SOURCE_DB_URL", "CSV_DIR", "TARGET_DB_PATH", "REPORTS_DIR", "ETL_MODE"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _count(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM consolidated_purchase_orders").fetchone()[0]


def test_cli_all_exits_0(workdir, capsys):
    assert main(["generate-data", "--orders-per-dc", "200"]) == 0
    assert main(["all"]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASSED" in out
    assert list((workdir / "reports").glob("validation_*.txt"))


def test_cli_explore_writes_report(workdir, capsys):
    main(["generate-data", "--orders-per-dc", "50"])
    assert main(["explore"]) == 0
    assert "TABLES FOUND: 2" in capsys.readouterr().out
    assert list((workdir / "reports").glob("exploration_*.txt"))


def test_cli_run_bad_url_exits_1_and_keeps_target(workdir, monkeypatch, capsys):
    main(["generate-data", "--orders-per-dc", "50"])
    assert main(["run"]) == 0
    before = _count(workdir / "data" / "target" / "warehouse.db")

    monkeypatch.setenv("SOURCE_DB_URL", f"sqlite:///{(workdir / 'nope' / 'x.db').as_posix()}")
    assert main(["run"]) == 1
    err = capsys.readouterr().err
    assert err.strip().splitlines()[-1].startswith("error:")
    assert _count(workdir / "data" / "target" / "warehouse.db") == before


def test_cli_validate_without_target_exits_1(workdir):
    assert main(["validate"]) == 1


def test_generate_data_rejects_non_sqlite_url(workdir, monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DB_URL", "mssql+pyodbc://user:pass@host/db")
    assert main(["generate-data"]) == 1
    assert "sqlite" in capsys.readouterr().err
