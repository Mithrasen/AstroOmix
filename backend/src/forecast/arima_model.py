"""ARIMA wrapped behind the common forecasting interface.

Read this before trusting an ARIMA number from this project
-----------------------------------------------------------
ARIMA assumes observations are **equally spaced in time**. The Inspiration4 CBC
timepoints are not, and it is not close: mission days are
-92, -44, -3, 4, 48, 85, 197, so consecutive gaps run 48, 41, 7, 44, 37, 112 days
— a 16x spread. Feeding that sequence to a textbook ARIMA treats the 7-day gap
around the flight and the 112-day gap out to R+194 as the same step, which is
simply false.

Rather than pretend otherwise, this wrapper is explicit about what it does:

    SARIMAX(y, exog=mission_day, order=(1,0,0), trend='c')

i.e. a linear trend in *actual mission day* (the exogenous regressor, which
respects the real spacing) plus an AR(1) term on the residuals (which does not).
Predictions at arbitrary days use the deterministic component, since an AR state
cannot be conditioned for a day that is not the next step in the sequence.

The uncertainty band is the stationary residual standard deviation,
sigma2 / (1 - phi^2), which is a real quantity from the fit — not a fabricated
interval.

The practical upshot: ARIMA is included for methodological comparison, and its
spacing assumption is the main reason to distrust it here relative to Prophet,
which models on a true date axis. This is stated in docs/methods.md too.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.forecast.common import DAY, VALUE, ForecastModel, check_training_frame

Z_95 = 1.959963985


class ArimaModel(ForecastModel):
    name = "arima"
    has_uncertainty = True

    def __init__(self, order: tuple[int, int, int] = (1, 0, 0)):
        self.order = order
        self._level = np.nan
        self._slope = np.nan
        self._sd = np.nan

    def fit(self, df: pd.DataFrame) -> None:
        # Imported here, not at module scope: statsmodels is ~40MB of RSS and is
        # only needed once a model is actually fitted. Cached forecast responses
        # never reach this line.
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        clean = check_training_frame(df)
        y = clean[VALUE].to_numpy(dtype=float)
        exog = clean[[DAY]].to_numpy(dtype=float)

        with warnings.catch_warnings():
            # At n=6 statsmodels warns about convergence. The warning is
            # legitimate; the limitation is documented rather than logged on
            # every request.
            warnings.simplefilter("ignore")
            result = SARIMAX(
                y, exog=exog, order=self.order, trend="c",
                # Stationarity MUST be enforced. With it off and only 5-6 points,
                # the optimiser happily fits an explosive AR (phi = 1.42 was
                # observed on a hemoglobin fold). An explosive AR has no
                # stationary level, so c/(1-phi) is meaningless and the model
                # predicted -4.7 for a series that lives at 14.
                enforce_stationarity=True,
                enforce_invertibility=True,
            ).fit(disp=False)

        params = dict(zip(result.param_names, result.params))
        self._slope = float(params.get("x1", 0.0))
        phi = float(params.get("ar.L1", 0.0))
        constant = float(params.get("intercept", 0.0))

        # statsmodels trap: with trend='c' AND an AR term, SARIMAX models
        #     y_t = beta*x_t + eta_t,   eta_t = c + phi*eta_{t-1} + e_t
        # so `intercept` is the constant of the ARMA *error* process, not the
        # regression level. The level is E[eta] = c / (1 - phi).
        #
        # Using the raw intercept puts the whole series in the wrong place: on
        # hemoglobin it gave a level of 18.16 against observations of 14.1-14.7,
        # and forecast 18.0 with a confident band that excluded every data point.
        self._level = constant / (1 - phi) if abs(phi) < 1 else constant

        sigma2 = float(params.get("sigma2", np.nan))
        # Stationary variance of an AR(1). Falls back to the innovation variance
        # if the fitted phi is non-stationary (possible with enforce off at n=6).
        variance = sigma2 / (1 - phi**2) if abs(phi) < 1 else sigma2
        self._sd = float(np.sqrt(variance)) if np.isfinite(variance) and variance > 0 else np.nan

    def predict(self, future_days: list[int]) -> pd.DataFrame:
        if not np.isfinite(self._slope):
            raise RuntimeError("fit() must be called before predict().")

        days = np.asarray(future_days, dtype=float)
        yhat = self._level + self._slope * days
        margin = Z_95 * self._sd  # NaN if the fit gave no usable variance

        return pd.DataFrame({
            "day": list(future_days),
            "yhat": yhat,
            "yhat_lower": yhat - margin,
            "yhat_upper": yhat + margin,
        })
