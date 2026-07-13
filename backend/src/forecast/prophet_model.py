"""Prophet wrapped behind the common forecasting interface.

Prophet models on dates, not integers, so mission days are mapped onto real
calendar dates anchored at the Inspiration4 launch (2021-09-16). That is a
faithful mapping — mission day 0 IS the launch date — not an invention.

All seasonalities are off. With 7 irregularly-spaced points spanning ~10 months
there is no weekly or yearly cycle to recover; leaving them on would let Prophet
fit seasonal wiggles to noise.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from src.forecast.common import DAY, VALUE, ForecastModel, check_training_frame

# Inspiration4 launch. Mission day 0.
LAUNCH_DATE = date(2021, 9, 16)

# Prophet/cmdstan chatter on every fit is noise in an API server.
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)


def _to_date(day: int) -> pd.Timestamp:
    return pd.Timestamp(LAUNCH_DATE + timedelta(days=int(day)))


class ProphetModel(ForecastModel):
    name = "prophet"
    has_uncertainty = True

    def __init__(self, interval_width: float = 0.95):
        self.interval_width = interval_width
        self._model: Prophet | None = None

    def fit(self, df: pd.DataFrame) -> None:
        # Imported here, not at module scope. Prophet is the heaviest dependency
        # in the project: it drags in cmdstanpy, which on first use may have to
        # locate — or compile — a Stan binary.
        #
        # That is exactly why this belongs in fit(). At module scope, a missing or
        # uncompiled Stan backend on Render takes down the whole app at boot, and
        # every endpoint 502s with a stack trace that has nothing to do with the
        # endpoint being called. Deferred to first use, the same failure shows up
        # as one slow (or failing) forecast request, with the rest of the API up
        # and serving. A localised failure beats a total one.
        from prophet import Prophet

        clean = check_training_frame(df)
        training = pd.DataFrame({
            "ds": clean[DAY].map(_to_date),
            "y": clean[VALUE].astype(float),
        })

        self._model = Prophet(
            growth="linear",
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=self.interval_width,
            # n=6 under LOO. The default changepoint prior lets Prophet bend the
            # trend hard enough to interpolate noise at this sample size.
            n_changepoints=0,
        )
        self._model.fit(training)

    def predict(self, future_days: list[int]) -> pd.DataFrame:
        if self._model is None:
            raise RuntimeError("fit() must be called before predict().")

        future = pd.DataFrame({"ds": [_to_date(d) for d in future_days]})
        forecast = self._model.predict(future)

        return pd.DataFrame({
            "day": list(future_days),
            "yhat": forecast["yhat"].to_numpy(),
            "yhat_lower": forecast["yhat_lower"].to_numpy(),
            "yhat_upper": forecast["yhat_upper"].to_numpy(),
        })
