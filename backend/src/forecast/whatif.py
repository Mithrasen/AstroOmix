"""What-if: extrapolate a fitted model past the last observed timepoint.

The last CBC draw is R+194 (mission day 197). `extra_days=30` asks what the model
says at day 227 — 30 days beyond any data.

This is extrapolation, and nothing in the leave-one-out scores validates it: LOO
measures how well a model interpolates the observed trajectory (see
eval_utils.py). A model can win on LOO and still extrapolate nonsensically. The
result therefore carries `extrapolated: true` and, for LightGBM, a flag that the
value is a boundary leaf rather than a trend.
"""

from __future__ import annotations

import math

import pandas as pd

from src.forecast.common import DAY, ForecastModel, check_training_frame


def _clean(value) -> float | None:
    """NaN is not valid JSON; a missing bound must serialise as null."""
    if value is None:
        return None
    number = float(value)
    return None if not math.isfinite(number) else number


def what_if(model: ForecastModel, df: pd.DataFrame, extra_days: int) -> dict:
    """Predict `extra_days` past the last observed mission day.

    The model must already be fitted on `df`.
    """
    if extra_days <= 0:
        raise ValueError(f"extra_days must be positive, got {extra_days}")

    clean = check_training_frame(df)
    last_day = int(clean[DAY].max())
    target_day = last_day + int(extra_days)

    prediction = model.predict([target_day]).iloc[0]

    result = {
        "model": model.name,
        "last_observed_day": last_day,
        "extra_days": int(extra_days),
        "day": target_day,
        "yhat": _clean(prediction["yhat"]),
        "yhat_lower": _clean(prediction.get("yhat_lower")),
        "yhat_upper": _clean(prediction.get("yhat_upper")),
        "has_uncertainty": model.has_uncertainty,
        "extrapolated": True,
    }

    # LightGBM returns a boundary leaf beyond its training range: a flat line, not
    # a forecast. Surface that rather than letting it read as a real projection.
    if "extrapolated" in prediction.index and bool(prediction["extrapolated"]):
        result["flat_extrapolation"] = True
        result["caveat"] = (
            "Tree models cannot extrapolate. This is the boundary leaf value "
            "(a flat continuation), not a projected trend."
        )

    return result
