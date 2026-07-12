"""Shared interface for the three forecasting models.

Every model takes a two-column frame of (day, value) — where `day` is a
**mission day** from `src.data.timepoints.to_mission_day`, never a raw 'L-92' /
'R+1' label — and predicts values at arbitrary future days.

Honest uncertainty
------------------
`predict` returns `yhat_lower` / `yhat_upper`. A model with no native notion of
predictive uncertainty (plain LightGBM point regression) returns **NaN** for
those bounds. It does not invent a band from residual spread and present it as a
prediction interval. A fabricated interval is worse than no interval: it looks
like information and is not.

Sample size
-----------
The whole panel is 7 timepoints. Under leave-one-out that means **six points per
fit**. Every model here is being run far below the regime it was designed for.
See docs/methods.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.data.timepoints import MISSION_DURATION_DAYS

DAY = "day"
VALUE = "value"

PREDICTION_COLUMNS = ["day", "yhat", "yhat_lower", "yhat_upper"]


class ForecastModel(ABC):
    """fit(df[day, value]) -> None; predict(days) -> df[day, yhat, lower, upper]."""

    name: str = "base"
    #: Whether the model produces a genuine predictive interval.
    has_uncertainty: bool = False

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> None:
        """Fit on a frame with columns `day` (mission day, int) and `value`."""

    @abstractmethod
    def predict(self, future_days: list[int]) -> pd.DataFrame:
        """Predict at the given mission days.

        Returns columns: day, yhat, yhat_lower, yhat_upper. Lower/upper are NaN
        when the model has no native uncertainty.
        """


def check_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise a training frame.

    Rejects raw timepoint labels loudly. A string like 'R+1' in the day column
    means someone skipped `to_mission_day`, and modelling on label order would
    silently treat the 3-day flight and the 112-day gap to R+194 as equal steps.
    """
    missing = {DAY, VALUE} - set(df.columns)
    if missing:
        raise ValueError(f"Training frame needs columns {DAY!r} and {VALUE!r}; missing {missing}")

    if not pd.api.types.is_numeric_dtype(df[DAY]):
        raise TypeError(
            f"{DAY!r} must be numeric mission days, got dtype {df[DAY].dtype}. "
            "Convert timepoint labels with src.data.timepoints.to_mission_day() "
            "before fitting — do not model on raw 'L-92'/'R+1' labels."
        )

    clean = df[[DAY, VALUE]].dropna().sort_values(DAY).reset_index(drop=True)
    if len(clean) < 3:
        raise ValueError(f"Need >=3 usable points to fit, got {len(clean)}.")
    return clean


def mission_phase(day: int) -> str:
    """preflight | inflight | recovery, from a mission day (launch = day 0)."""
    if day < 0:
        return "preflight"
    if day <= MISSION_DURATION_DAYS:
        return "inflight"
    return "recovery"


def empty_predictions(days: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "day": days,
        "yhat": float("nan"),
        "yhat_lower": float("nan"),
        "yhat_upper": float("nan"),
    })
