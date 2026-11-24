"""Post-load data-quality checks on the consolidated table."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from orders_etl.schema import (
    DISTRIBUTION_CENTERS,
    QUARANTINE_TABLE,
    TARGET_TABLE,
    VALID_STATUSES,
)

Status = Literal["PASS", "WARN", "FAIL", "ERROR"]


@dataclass(frozen=True)
class Expectations:
    min_rows: int = 1
    max_rows: int | None = None
    date_min: str = "2023-01-01"
    date_max: str = "2025-12-31"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(c.status in ("FAIL", "ERROR") for c in self.checks)

    def count(self, status: Status) -> int:
        return sum(c.status == status for c in self.checks)

    def render(self) -> str:
        line = "=" * 70
        out = [
            line,
            "VALIDATION REPORT - CONSOLIDATED PURCHASE ORDERS",
            line,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Table: {TARGET_TABLE}",
            "",
            f"Checks: {len(self.checks)} | Passed: {self.count('PASS')} | "
            f"Warnings: {self.count('WARN')} | Failed: {self.count('FAIL')} | "
            f"Errors: {self.count('ERROR')}",
            "",
        ]
        for i, c in enumerate(self.checks, 1):
            out.append(f"{i}. [{c.status}] {c.name}" + (f" - {c.detail}" if c.detail else ""))
        if not self.ok:
            verdict = "FAILED"
        elif self.count("WARN"):
            verdict = "PASSED WITH WARNINGS"
        else:
            verdict = "PASSED"
        out += ["", line, f"RESULT: {verdict}", line]
        return "\n".join(out)


class DataValidator:
    def __init__(self, db_path: Path, expectations: Expectations | None = None):
        self.db_path = Path(db_path)
        self.exp = expectations or Expectations()

    def run(self) -> ValidationReport:
        report = ValidationReport()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self._conn = conn
            report.checks.append(self._safe("Table exists", self._table_exists))
            if report.checks[0].status != "PASS":
                return report
            for name, check in (
                ("Row count", self._row_count),
                ("Duplicate keys", self._duplicates),
                ("Critical nulls", self._critical_nulls),
                ("Distribution centers", self._distribution_centers),
                ("Valid statuses", self._statuses),
                ("Date range", self._date_range),
                ("Numeric consistency", self._numeric_consistency),
                ("Quarantined rows", self._quarantine),
            ):
                report.checks.append(self._safe(name, check))
        return report

    # -- helpers ---------------------------------------------------------------------------
    def _safe(self, name: str, check: Callable[[], tuple[Status, str]]) -> CheckResult:
        try:
            status, detail = check()
        except sqlite3.Error as exc:
            status, detail = "ERROR", str(exc)
        return CheckResult(name, status, detail)

    def _scalar(self, sql: str, params: tuple = ()) -> object:
        return self._conn.execute(sql, params).fetchone()[0]

    # -- checks ----------------------------------------------------------------------------
    def _table_exists(self) -> tuple[Status, str]:
        found = self._scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?", (TARGET_TABLE,)
        )
        return ("PASS", "found") if found else ("FAIL", f"table {TARGET_TABLE!r} not found")

    def _row_count(self) -> tuple[Status, str]:
        total = int(self._scalar(f"SELECT COUNT(*) FROM {TARGET_TABLE}"))
        upper = self.exp.max_rows if self.exp.max_rows is not None else float("inf")
        in_range = self.exp.min_rows <= total <= upper
        return ("PASS" if in_range else "WARN"), f"{total:,} rows"

    def _duplicates(self) -> tuple[Status, str]:
        dups = self._scalar(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM {TARGET_TABLE} "
            "GROUP BY id, distribution_center HAVING COUNT(*) > 1)"
        )
        return ("PASS", "0 duplicate keys") if dups == 0 else ("FAIL", f"{dups} duplicate keys")

    def _critical_nulls(self) -> tuple[Status, str]:
        nulls = {
            col: self._scalar(f"SELECT COUNT(*) FROM {TARGET_TABLE} WHERE {col} IS NULL")
            for col in ("id", "distribution_center", "source")
        }
        bad = {k: v for k, v in nulls.items() if v}
        return ("PASS", "no nulls in key columns") if not bad else ("FAIL", f"nulls: {bad}")

    def _distribution_centers(self) -> tuple[Status, str]:
        found = {
            r[0]
            for r in self._conn.execute(f"SELECT DISTINCT distribution_center FROM {TARGET_TABLE}")
        }
        unknown = found - set(DISTRIBUTION_CENTERS)
        missing = set(DISTRIBUTION_CENTERS) - found
        if unknown:
            return "FAIL", f"unexpected centers: {sorted(unknown)}"
        if missing:
            return "WARN", f"missing centers: {sorted(missing)}"
        return "PASS", f"{sorted(found)}"

    def _statuses(self) -> tuple[Status, str]:
        found = {r[0] for r in self._conn.execute(f"SELECT DISTINCT status FROM {TARGET_TABLE}")}
        unknown = {s for s in found if s not in VALID_STATUSES}
        return (
            ("PASS", f"{len(found)} statuses")
            if not unknown
            else (
                "WARN",
                f"unexpected statuses: {sorted(map(str, unknown))}",
            )
        )

    def _date_range(self) -> tuple[Status, str]:
        lo, hi = self._conn.execute(
            f"SELECT MIN(created_at), MAX(created_at) FROM {TARGET_TABLE}"
        ).fetchone()
        if lo is None:
            return "WARN", "no created_at values"
        ok = lo >= self.exp.date_min and hi[:10] <= self.exp.date_max
        return ("PASS" if ok else "WARN"), f"created_at {lo} .. {hi}"

    def _numeric_consistency(self) -> tuple[Status, str]:
        negatives = self._scalar(
            f"SELECT COUNT(*) FROM {TARGET_TABLE} "
            "WHERE received_quantity < 0 OR requested_quantity < 0 OR total < 0"
        )
        over = self._scalar(
            f"SELECT COUNT(*) FROM {TARGET_TABLE} WHERE received_quantity > requested_quantity"
        )
        if negatives:
            return "FAIL", f"{negatives:,} rows with negative values"
        if over:
            return "WARN", f"{over:,} rows with received_quantity > requested_quantity"
        return "PASS", "no negative or over-delivered rows"

    def _quarantine(self) -> tuple[Status, str]:
        exists = self._scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            (QUARANTINE_TABLE,),
        )
        if not exists:
            return "PASS", "no quarantine table"
        by_reason = dict(
            self._conn.execute(
                f"SELECT quarantine_reason, COUNT(*) FROM {QUARANTINE_TABLE} GROUP BY 1 ORDER BY 1"
            )
        )
        if not by_reason:
            return "PASS", "0 rows set aside"
        detail = ", ".join(f"{reason}: {n:,}" for reason, n in by_reason.items())
        return "WARN", f"{detail} - review {QUARANTINE_TABLE}"
