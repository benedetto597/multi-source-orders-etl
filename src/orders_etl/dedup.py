"""Latest-wins deduplication on the business key (id, distribution_center)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

KEY = ["id", "distribution_center"]


@dataclass(frozen=True)
class DedupStats:
    initial: int
    final: int
    removed: int
    rows_in_duplicate_groups: int


def remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, DedupStats]:
    """Keep one row per key: the most recent ``updated_at`` (falling back to ``created_at``).

    Rows with no usable date lose to any dated row; on an exact tie the row that appears
    later in the input (the newer delivery, e.g. a CSV after the SQL snapshot) wins.
    """
    work = df.assign(
        _ref=df["updated_at"].fillna(df["created_at"]),
        _order=np.arange(len(df)),
    )
    in_groups = int(work.duplicated(subset=KEY, keep=False).sum())
    work = work.sort_values(
        by=[*KEY, "_ref", "_order"],
        ascending=[True, True, False, False],
        na_position="last",
        kind="mergesort",
    )
    out = (
        work.drop_duplicates(subset=KEY, keep="first")
        .drop(columns=["_ref", "_order"])
        .reset_index(drop=True)
    )
    stats = DedupStats(
        initial=len(df),
        final=len(out),
        removed=len(df) - len(out),
        rows_in_duplicate_groups=in_groups,
    )
    logger.info(
        "Deduplicated: %s -> %s rows (%s removed)",
        f"{stats.initial:,}",
        f"{stats.final:,}",
        f"{stats.removed:,}",
    )
    return out, stats
