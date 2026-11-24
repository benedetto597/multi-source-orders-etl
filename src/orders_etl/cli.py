"""Command-line entry point: ``orders-etl {generate-data,explore,run,validate,all}``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy.engine import make_url

from orders_etl.config import Settings
from orders_etl.explore import explore_source
from orders_etl.pipeline import PipelineResult, run_pipeline
from orders_etl.synthetic import generate
from orders_etl.validate import DataValidator, Expectations

logger = logging.getLogger("orders_etl")


def _save_report(settings: Settings, prefix: str, text: str) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def format_result(r: PipelineResult) -> str:
    lines = [
        f"ETL finished ({r.mode}) in {r.seconds:.2f}s",
        f"  extracted rows        : {r.extracted:,}",
        f"  duplicates removed    : {r.dedup.removed:,}",
        f"  rows in target        : {r.load.total:,}",
        f"  duplicate keys        : {r.load.duplicate_keys}",
        "  by distribution center: " + ", ".join(f"{k}={v:,}" for k, v in r.load.by_dc.items()),
        "  by source             : " + ", ".join(f"{k}={v:,}" for k, v in r.load.by_source.items()),
    ]
    if r.upsert is not None:
        lines.append(
            f"  upsert                : {r.upsert.inserted:,} inserted, "
            f"{r.upsert.updated:,} updated, {r.upsert.skipped_stale:,} stale skipped"
        )
    return "\n".join(lines)


def _cmd_generate(settings: Settings, args: argparse.Namespace) -> int:
    url = make_url(settings.source_db_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError("generate-data needs a file-based sqlite SOURCE_DB_URL")
    summary = generate(Path(url.database), settings.csv_dir, args.orders_per_dc, args.seed)
    print(
        f"Synthetic data written: SQL rows {summary.sql_rows}, "
        f"CSV rows {summary.csv_rows} in {summary.csv_files} files"
    )
    return 0


def _cmd_explore(settings: Settings, args: argparse.Namespace) -> int:
    report = explore_source(settings.source_db_url)
    print(report)
    print(f"\nReport saved to {_save_report(settings, 'exploration', report)}")
    return 0


def _cmd_run(settings: Settings, args: argparse.Namespace) -> int:
    print(format_result(run_pipeline(settings)))
    return 0


def _cmd_validate(settings: Settings, args: argparse.Namespace) -> int:
    if not settings.target_db_path.exists():
        raise FileNotFoundError(f"target database not found: {settings.target_db_path}")
    report = DataValidator(settings.target_db_path, Expectations(min_rows=args.min_rows)).run()
    text = report.render()
    print(text)
    print(f"Report saved to {_save_report(settings, 'validation', text)}")
    return 0 if report.ok else 1


def _cmd_all(settings: Settings, args: argparse.Namespace) -> int:
    _cmd_run(settings, args)
    return _cmd_validate(settings, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orders-etl",
        description="Consolidate purchase orders from a legacy SQL source and CSV drops.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate-data", help="create the synthetic source database and CSVs")
    gen.add_argument("--orders-per-dc", type=int, default=3000)
    gen.add_argument("--seed", type=int, default=42)
    gen.set_defaults(func=_cmd_generate)

    sub.add_parser("explore", help="profile the source database").set_defaults(func=_cmd_explore)
    sub.add_parser("run", help="run the ETL (ETL_MODE=full|incremental)").set_defaults(
        func=_cmd_run
    )
    for name, func, help_ in (
        ("validate", _cmd_validate, "run data-quality checks on the target"),
        ("all", _cmd_all, "run the ETL, then validate"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--min-rows", type=int, default=1)
        p.set_defaults(func=func)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(find_dotenv(usecwd=True))
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stderr,
        force=True,
    )
    try:
        return args.func(Settings.from_env(), args)
    except Exception as exc:  # CLI boundary: one readable line, details with -v
        logger.debug("Command failed", exc_info=True)
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
