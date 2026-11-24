from orders_etl.explore import explore_source
from orders_etl.synthetic import generate


def test_explore_lists_both_tables_and_types(tmp_path):
    db = tmp_path / "src.db"
    generate(db, tmp_path / "csv", orders_per_dc=50, seed=3)
    report = explore_source(f"sqlite:///{db.as_posix()}")
    assert "TABLES FOUND: 2" in report
    for table in ("purchase_orders_dc_1", "purchase_orders_dc_2"):
        assert f"TABLE: {table}" in report
    assert "requested_quantity" in report and "TEXT" in report and "INTEGER" in report
    assert report.count("Rows: 50") == 2
    assert report.count("Duplicate ids: 0") == 2
    assert "created_at range:" in report
