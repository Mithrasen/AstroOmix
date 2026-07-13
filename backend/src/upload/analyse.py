"""Run analysis on validated uploaded data.

No modelling is implemented here. This module only chooses an engine and calls
the existing ones:

    src.abtest.rnaseq.differential_expression   NB GLM (default for uploads)
    src.abtest.deseq.run_deseq2                 DESeq2 (only if ALLOW_REFRESH)
    src.forecast.eval_utils.compare             LOO-CV model comparison
    src.forecast.whatif.what_if                 extrapolation
"""

from __future__ import annotations

import warnings

import pandas as pd

from src.abtest.rnaseq import differential_expression
from src.forecast.arima_model import ArimaModel
from src.forecast.eval_utils import compare
from src.forecast.lightgbm_model import LightGBMModel
from src.forecast.prophet_model import ProphetModel
from src.forecast.whatif import what_if

MODELS = {"prophet": ProphetModel, "arima": ArimaModel, "lightgbm": LightGBMModel}

CURVE_POINTS = 60

# Engines available for an uploaded counts matrix, and what each costs.
#
# nb_glm is the default and the only one offered in the deployed app. See
# src/upload/validate.py for the measurements: DESeq2 costs ~2.4 GB regardless of
# how small the upload is, because the cost is its worker pool and not the matrix.
ENGINES = {
    "nb_glm": {
        "label": "Negative-binomial GLM",
        "note": (
            "Single-process statsmodels; ~220 MB peak even at the size cap. "
            "This is NOT DESeq2: dispersions are unshrunk method-of-moments "
            "estimates, so very small p-values are over-confident. The gene "
            "ranking is trustworthy; the extreme tail of the p-value scale is not."
        ),
        "requires_allow_refresh": False,
    },
    "deseq2": {
        "label": "DESeq2 (pydeseq2)",
        "note": (
            "Empirical-Bayes dispersion shrinkage — the better model. But it peaks "
            "at ~2.4 GB regardless of upload size, which exceeds the deployed app's "
            "memory budget, so it is only available where ALLOW_REFRESH=true."
        ),
        "requires_allow_refresh": True,
    },
}


def run_de(counts: pd.DataFrame, engine: str = "nb_glm") -> pd.DataFrame:
    """Differential expression on an uploaded counts matrix.

    Returns a table with base_mean / log2fc / pvalue / padj, whichever engine ran,
    so the display code does not have to branch.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        if engine == "deseq2":
            # Imported lazily: pydeseq2 is ~100 MB of RSS and the deployed app
            # never reaches this branch (it is gated on ALLOW_REFRESH).
            from src.abtest.deseq import deseq2_on_counts

            return deseq2_on_counts(counts, label="your upload")

        results = differential_expression(counts)

    # The NB GLM table carries extra columns (dispersion, n_flight, n_ground).
    # Keep them — they are informative — but put the shared four first.
    ordered = ["base_mean", "log2fc", "pvalue", "padj"]
    rest = [c for c in results.columns if c not in ordered]
    return results[ordered + rest]


def run_forecast(series: pd.DataFrame, extra_days: int, unit: str = "value") -> dict:
    """Model comparison + what-if on an uploaded (day, value) series.

    Same shape of payload as the CBC forecast route, so the page renders it with
    the same code.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        comparison = compare(MODELS, series)

        last_day = int(series["day"].max())
        first_day = int(series["day"].min())
        horizon = last_day + max(extra_days, 0)
        step = max((horizon - first_day) // CURVE_POINTS, 1)
        days = list(range(first_day, horizon + 1, step))
        if days[-1] != horizon:
            days.append(horizon)

        curves, scenarios = {}, {}
        for name, factory in MODELS.items():
            model = factory()
            model.fit(series)
            predicted = model.predict(days)

            curves[name] = {
                "has_uncertainty": model.has_uncertainty,
                "points": [
                    {
                        "day": int(row["day"]),
                        "yhat": _finite(row["yhat"]),
                        "yhat_lower": _finite(row.get("yhat_lower")),
                        "yhat_upper": _finite(row.get("yhat_upper")),
                    }
                    for _, row in predicted.iterrows()
                ],
            }
            if extra_days > 0:
                scenarios[name] = what_if(model, series, extra_days)

    metrics = {
        name: {
            "mae": _finite(m["mae"]),
            "rmse": _finite(m["rmse"]),
            "mape": _finite(m["mape"]),
            "n_folds": m["n_folds"],
            "n_failed": m["n_failed"],
        }
        for name, m in comparison["models"].items()
    }

    best = comparison["best_by_mae"]
    warning = None
    if best and not MODELS[best].has_uncertainty:
        warning = (
            f"{best} has the lowest LOO MAE, but it is a point regressor with no "
            "predictive interval and cannot extrapolate past the last observed day. "
            "Do not read 'best' as 'best forecaster' — the LOO score only measures "
            "interpolation of the observed points."
        )

    return {
        "analyte": "uploaded series",
        "unit": unit,
        "crew": "uploaded",
        "n_timepoints": len(series),
        "observed": [
            {"day": int(r["day"]), "value": _finite(r["value"])}
            for _, r in series.iterrows()
        ],
        "curves": curves,
        "comparison": {
            "metrics": metrics,
            "best_by_mae": best,
            "best_by_mae_warning": warning,
            "method": "leave-one-out cross-validation across timepoints",
        },
        "whatif": scenarios if extra_days > 0 else None,
        "caveat": (
            f"Your own data: {len(series)} timepoints. Everything the CBC caveats say "
            "applies here too — LOO-CV measures interpolation of the observed points "
            "and does not validate the what-if extrapolation."
        ),
    }


def _finite(value):
    """NaN is not valid JSON and must not be rendered as a number."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number or number in (float("inf"), float("-inf")) else number
