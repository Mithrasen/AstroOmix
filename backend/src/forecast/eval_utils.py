"""Leave-one-out cross-validation for the forecasting models.

Why LOO and not a train/test split
----------------------------------
There are 7 timepoints. A conventional split — say the last two held out —
leaves 5 points to fit and evaluates on 2. Two points is not an evaluation; a
single noisy observation swings the MAE by a large fraction, and the "test set"
would be entirely the recovery tail, so the score would say nothing about how a
model handles the pre-flight baseline or the flight response.

Leave-one-out uses all 7 points as test points, one at a time, each time fitting
on the other 6. Every observation contributes to the score exactly once, which is
the most evaluation signal that 7 points can support.

What LOO here does NOT do
-------------------------
It is not a forecasting backtest. Holding out an *interior* timepoint and fitting
on points that come after it lets the model see the future. That is legitimate
for asking "can this model describe the shape of this series?", which is the
question here, but it is not the same as "could this model have predicted the
next draw?". With one post-return trend and 7 points, a rolling-origin backtest
would leave 2-3 usable folds — too few to rank three models.

So: these scores compare how well each model *interpolates the observed
trajectory*, not how well it forecasts unseen future. The what-if extrapolation
is reported separately and is not validated by these numbers. See docs/methods.md.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from src.forecast.common import DAY, VALUE, ForecastModel, check_training_frame

ModelFactory = Callable[[], ForecastModel]

# MAPE explodes as the true value approaches zero. CBC analytes include
# percentages that are legitimately near zero (basophils run ~0.5%), so a fold
# with y_true ~ 0 would dominate the mean and produce a meaningless number.
MAPE_FLOOR = 1e-6


def leave_one_out(factory: ModelFactory, df: pd.DataFrame) -> pd.DataFrame:
    """Hold out each timepoint once; fit on the rest; predict the held-out point.

    Returns one row per fold: day, y_true, y_pred.
    """
    clean = check_training_frame(df)

    folds = []
    for position in range(len(clean)):
        test = clean.iloc[[position]]
        train = clean.drop(clean.index[position])

        model = factory()
        try:
            model.fit(train)
            day = int(test[DAY].iloc[0])
            prediction = model.predict([day])
            y_pred = float(prediction["yhat"].iloc[0])
        except Exception as error:
            # A fold that fails to fit is recorded as NaN, not silently dropped —
            # a model that only converges on some folds should look worse, and be
            # visibly so, rather than being scored on its easy folds alone.
            day = int(test[DAY].iloc[0])
            y_pred = np.nan
            folds.append({"day": day, "y_true": float(test[VALUE].iloc[0]),
                          "y_pred": y_pred, "error": str(error)[:120]})
            continue

        folds.append({"day": day, "y_true": float(test[VALUE].iloc[0]),
                      "y_pred": y_pred, "error": None})

    return pd.DataFrame(folds)


def score(folds: pd.DataFrame) -> dict:
    """Aggregate MAE / RMSE / MAPE across LOO folds."""
    usable = folds.dropna(subset=["y_pred"])
    n_failed = len(folds) - len(usable)

    if usable.empty:
        return {"mae": None, "rmse": None, "mape": None,
                "n_folds": len(folds), "n_failed": n_failed}

    error = usable["y_pred"].to_numpy() - usable["y_true"].to_numpy()
    truth = usable["y_true"].to_numpy()

    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error**2)))

    denominator = np.abs(truth)
    safe = denominator > MAPE_FLOOR
    mape = (
        float(np.mean(np.abs(error[safe] / denominator[safe])) * 100)
        if safe.any() else None
    )

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "n_folds": len(folds),
        "n_failed": n_failed,
    }


def compare(factories: dict[str, ModelFactory], df: pd.DataFrame) -> dict:
    """Run LOO for each model and rank by MAE (lowest wins)."""
    table = {}
    for name, factory in factories.items():
        folds = leave_one_out(factory, df)
        metrics = score(folds)
        metrics["folds"] = folds.to_dict(orient="records")
        table[name] = metrics

    scored = {n: m["mae"] for n, m in table.items() if m["mae"] is not None}
    best = min(scored, key=scored.get) if scored else None

    return {"models": table, "best_by_mae": best}
