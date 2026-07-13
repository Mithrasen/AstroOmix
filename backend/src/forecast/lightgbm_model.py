"""LightGBM wrapped behind the common forecasting interface.

Features
--------
LightGBM has no time axis of its own, so the time structure must be handed to it
as features:

    mission_day     the real day (launch = 0), so spacing is respected
    phase           preflight / inflight / recovery, one-hot

**No lag features.** With 7 timepoints — six under leave-one-out — a single lag
would cost another row and leave five, and a lag-1 feature across a 112-day gap
does not mean the same thing as a lag-1 feature across a 7-day gap. At this n,
lags would encode noise and irregular spacing rather than autocorrelation. This
is a deliberate omission, not an oversight.

Two hard limits, stated plainly
-------------------------------
1. **No uncertainty.** This is a point regressor. `yhat_lower`/`yhat_upper` are
   NaN. We do not manufacture a band from residual spread and dress it up as a
   prediction interval.

2. **It cannot extrapolate.** Gradient-boosted trees predict a constant outside
   the range of their training data — the value of the boundary leaf. Asked for
   a day beyond the last observed timepoint (R+194 = day 197), LightGBM returns
   a flat line, not a trend. That makes it structurally unsuited to the what-if
   scenario, and `predict` flags such days via `extrapolated` so callers cannot
   mistake a flat continuation for a forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.forecast.common import DAY, VALUE, ForecastModel, check_training_frame, mission_phase

PHASES = ("preflight", "inflight", "recovery")


def build_features(days) -> pd.DataFrame:
    frame = pd.DataFrame({"mission_day": np.asarray(days, dtype=float)})
    phases = [mission_phase(int(d)) for d in days]
    for phase in PHASES:
        frame[f"phase_{phase}"] = [1.0 if p == phase else 0.0 for p in phases]
    return frame


class LightGBMModel(ForecastModel):
    name = "lightgbm"
    has_uncertainty = False  # point predictions only; bands stay NaN

    def __init__(self):
        self._model: LGBMRegressor | None = None
        self._max_training_day: float = np.nan

    def fit(self, df: pd.DataFrame) -> None:
        # Imported here, not at module scope: LightGBM loads a native binary and
        # is only needed once a model is actually fitted.
        from lightgbm import LGBMRegressor

        clean = check_training_frame(df)
        features = build_features(clean[DAY].to_numpy())
        target = clean[VALUE].to_numpy(dtype=float)
        self._max_training_day = float(clean[DAY].max())

        self._model = LGBMRegressor(
            # Tuned down hard: with six rows the defaults (20 leaves, 20 samples
            # per leaf) cannot even form a split, and LightGBM silently returns
            # the target mean for every input.
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=4,
            min_child_samples=1,
            min_child_weight=1e-3,
            min_split_gain=0.0,
            verbose=-1,
        )
        self._model.fit(features, target)

    def predict(self, future_days: list[int]) -> pd.DataFrame:
        if self._model is None:
            raise RuntimeError("fit() must be called before predict().")

        yhat = self._model.predict(build_features(future_days))

        return pd.DataFrame({
            "day": list(future_days),
            "yhat": yhat,
            # No native uncertainty. NaN, not a fabricated band.
            "yhat_lower": np.nan,
            "yhat_upper": np.nan,
            # True where the tree is returning a boundary leaf, i.e. a flat line
            # rather than a forecast.
            "extrapolated": [d > self._max_training_day for d in future_days],
        })
