"""Set aside rows that cannot be loaded, so one bad record never aborts the whole run."""

from __future__ import annotations

import logging

import pandas as pd

from orders_etl.schema import DISTRIBUTION_CENTERS

logger = logging.getLogger(__name__)

REASON_COLUMN = "quarantine_reason"


def split_invalid(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(valid, rejected)``; ``rejected`` carries a ``quarantine_reason`` column.

    A row is rejected when its business key is unusable: no ``id`` (checked first), or a
    ``distribution_center`` outside the known centers (e.g. a CSV order code that could not
    be attributed).
    """
    reasons = pd.Series(None, index=df.index, dtype="object")
    reasons[~df["distribution_center"].isin(DISTRIBUTION_CENTERS)] = "unknown distribution center"
    reasons[df["id"].isna()] = "missing id"
    rejected_mask = reasons.notna()

    valid = df[~rejected_mask].reset_index(drop=True)
    rejected = df[rejected_mask].assign(**{REASON_COLUMN: reasons[rejected_mask]})
    rejected = rejected.reset_index(drop=True)
    if not rejected.empty:
        logger.warning(
            "Quarantined %s rows: %s",
            f"{len(rejected):,}",
            rejected[REASON_COLUMN].value_counts().to_dict(),
        )
    return valid, rejected
