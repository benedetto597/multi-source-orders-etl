"""Runtime settings, read from environment variables (optionally via a .env file)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Mode = Literal["full", "incremental"]
_MODES: tuple[str, ...] = ("full", "incremental")


@dataclass(frozen=True)
class Settings:
    source_db_url: str
    csv_dir: Path
    target_db_path: Path
    reports_dir: Path
    mode: Mode
    overlap_days: int
    state_path: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``env`` (defaults to ``os.environ``)."""
        env = os.environ if env is None else env
        mode = env.get("ETL_MODE", "full").strip().lower()
        if mode not in _MODES:
            raise ValueError(f"ETL_MODE must be one of {_MODES}, got {mode!r}")
        return cls(
            source_db_url=env.get("SOURCE_DB_URL", "sqlite:///data/source/legacy_source.db"),
            csv_dir=Path(env.get("CSV_DIR", "data/csv")),
            target_db_path=Path(env.get("TARGET_DB_PATH", "data/target/warehouse.db")),
            reports_dir=Path(env.get("REPORTS_DIR", "reports")),
            mode=mode,  # type: ignore[arg-type]
            overlap_days=int(env.get("INCREMENTAL_OVERLAP_DAYS", "30")),
            state_path=Path(env.get("ETL_STATE_PATH", "data/target/etl_state.json")),
        )
