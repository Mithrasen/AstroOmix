"""GET /api/forecast/{analyte} — I4 CBC trajectory forecasting.

Three models (Prophet, ARIMA, LightGBM) fitted to one CBC analyte over the
mission timeline, compared by leave-one-out CV, with an optional what-if
extrapolation past the last draw.

Sample size is 4 crew x 7 timepoints. Every response carries that caveat
explicitly — the model comparison here is a demonstration of method, not a
clinical result. See docs/methods.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import warnings

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from src.data.loaders import CACHE_DIR, fetch_i4_cbc
from src.forecast.arima_model import ArimaModel
from src.forecast.eval_utils import compare
from src.forecast.lightgbm_model import LightGBMModel
from src.forecast.prophet_model import ProphetModel
from src.forecast.whatif import what_if

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

FORECAST_CACHE = CACHE_DIR / "forecast"

MODELS = {"prophet": ProphetModel, "arima": ArimaModel, "lightgbm": LightGBMModel}

CAVEAT = (
    "n = 4 crew x 7 timepoints. Model comparison is illustrative methodology, "
    "not a clinical claim. LOO-CV measures interpolation of the observed "
    "trajectory, and does not validate the what-if extrapolation."
)

# Points on the plotted curve. The observed span is day -92 to 197; a ~4-day grid
# gives a smooth line without inflating the payload.
CURVE_STEP_DAYS = 4


def _series(analyte: str, crew: str) -> tuple[pd.DataFrame, str]:
    """Return the (day, value) frame for one analyte, plus its unit."""
    cbc = fetch_i4_cbc()
    subset = cbc[cbc.analyte == analyte]
    unit = str(subset["unit"].iloc[0])

    if crew == "mean":
        # Aggregate across crew per timepoint. n=4 per individual is very thin,
        # so the crew mean is the primary mode.
        series = (
            subset.groupby("mission_day", as_index=False)["value"]
            .mean()
            .rename(columns={"mission_day": "day"})
        )
    else:
        series = (
            subset[subset.crew == crew][["mission_day", "value"]]
            .rename(columns={"mission_day": "day"})
        )

    series = series.dropna().sort_values("day").reset_index(drop=True)
    return series, unit


def _valid_analytes() -> list[str]:
    """The 20 real CBC analyte names. An unvalidated analyte would let a caller
    pass anything into a groupby and get an empty series back — same
    allowlist-not-arbitrary-input rule as the abtest accession restriction."""
    return sorted(fetch_i4_cbc()["analyte"].unique())


def _valid_crew() -> list[str]:
    return ["mean", *sorted(fetch_i4_cbc()["crew"].unique())]


def _clean(value) -> float | None:
    """NaN is not valid JSON. Missing bounds serialise as null, never as a number."""
    if value is None:
        return None
    number = float(value)
    return None if not math.isfinite(number) else round(number, 4)


def _cache_path(analyte: str, crew: str, extra_days: int):
    key = hashlib.sha256(
        json.dumps({"analyte": analyte, "crew": crew, "extra_days": extra_days},
                   sort_keys=True).encode()
    ).hexdigest()[:12]
    return FORECAST_CACHE / f"{analyte}__{crew}__{extra_days}__{key}.json"


def _build(analyte: str, crew: str, extra_days: int) -> dict:
    series, unit = _series(analyte, crew)
    if len(series) < 3:
        raise HTTPException(
            status_code=422,
            detail=f"{analyte!r} for crew={crew!r} has only {len(series)} usable "
                   "timepoints; need at least 3 to fit.",
        )

    last_day = int(series["day"].max())
    horizon = last_day + max(extra_days, 0)
    curve_days = list(range(int(series["day"].min()), horizon + 1, CURVE_STEP_DAYS))
    if curve_days[-1] != horizon:
        curve_days.append(horizon)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comparison = compare(MODELS, series)

        curves = {}
        scenarios = {}
        for name, factory in MODELS.items():
            model = factory()
            model.fit(series)

            predicted = model.predict(curve_days)
            curves[name] = {
                "has_uncertainty": model.has_uncertainty,
                "points": [
                    {
                        "day": int(row["day"]),
                        "yhat": _clean(row["yhat"]),
                        "yhat_lower": _clean(row.get("yhat_lower")),
                        "yhat_upper": _clean(row.get("yhat_upper")),
                    }
                    for _, row in predicted.iterrows()
                ],
            }

            if extra_days > 0:
                scenarios[name] = what_if(model, series, extra_days)

    metrics = {
        name: {
            "mae": _clean(m["mae"]),
            "rmse": _clean(m["rmse"]),
            "mape": _clean(m["mape"]),
            "n_folds": m["n_folds"],
            "n_failed": m["n_failed"],
        }
        for name, m in comparison["models"].items()
    }

    best = comparison["best_by_mae"]

    # "Best by MAE" ranks INTERPOLATION of the observed points. It does not mean
    # "best forecaster". LightGBM in particular often wins the LOO score and is
    # simultaneously the only model that cannot extrapolate at all — its what-if
    # is a flat boundary leaf. Surface that contradiction rather than letting a
    # caller read best_by_mae and plot the least valid extrapolation.
    best_warning = None
    if best and not MODELS[best].has_uncertainty:
        best_warning = (
            f"{best} has the lowest LOO MAE, but it is a point regressor with no "
            "predictive interval and cannot extrapolate past the last observed "
            "day. Do not read 'best' as 'best forecaster' — the LOO score only "
            "measures interpolation of the observed points."
        )

    return {
        "analyte": analyte,
        "unit": unit,
        "crew": crew,
        "n_timepoints": len(series),
        "observed": [
            {"day": int(row["day"]), "value": _clean(row["value"])}
            for _, row in series.iterrows()
        ],
        "curves": curves,
        "comparison": {
            "metrics": metrics,
            "best_by_mae": best,
            "best_by_mae_warning": best_warning,
            "method": "leave-one-out cross-validation across timepoints",
        },
        "whatif": scenarios if extra_days > 0 else None,
        "caveat": CAVEAT,
    }


@router.get("/{analyte}")
def forecast(
    analyte: str,
    crew: str = Query("mean", description="'mean' (across all 4 crew) or a crew id."),
    extra_days: int = Query(0, ge=0, le=365,
                            description="Extrapolate this many days past the last draw."),
    refresh: bool = Query(False, description="Bypass the cache."),
) -> dict:
    analytes = _valid_analytes()
    if analyte not in analytes:
        raise HTTPException(
            status_code=404,
            detail=f"{analyte!r} is not a CBC analyte. Available: {analytes}",
        )

    crews = _valid_crew()
    if crew not in crews:
        raise HTTPException(
            status_code=404, detail=f"{crew!r} is not valid. Available: {crews}",
        )

    path = _cache_path(analyte, crew, extra_days)
    if path.is_file() and not refresh:
        return json.loads(path.read_text())

    payload = _build(analyte, crew, extra_days)

    FORECAST_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


@router.get("")
def list_analytes() -> dict:
    """The analytes and crew ids that /api/forecast/{analyte} will accept."""
    return {"analytes": _valid_analytes(), "crew": _valid_crew()}
