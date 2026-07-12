import warnings

import numpy as np
import pandas as pd
import pytest

from src.data.loaders import fetch_i4_cbc
from src.data.timepoints import to_mission_day
from src.forecast.arima_model import ArimaModel
from src.forecast.common import check_training_frame, mission_phase
from src.forecast.eval_utils import compare, leave_one_out, score
from src.forecast.lightgbm_model import LightGBMModel
from src.forecast.prophet_model import ProphetModel
from src.forecast.whatif import what_if

MODELS = {"prophet": ProphetModel, "arima": ArimaModel, "lightgbm": LightGBMModel}

# Two analytes with visibly different shapes:
#   absolute_neutrophils — rises into flight, then recovers (a real trajectory)
#   hemoglobin           — essentially flat across the whole mission
SHAPED = "absolute_neutrophils"
FLAT = "hemoglobin"


@pytest.fixture(scope="module")
def cbc():
    return fetch_i4_cbc()


def series_for(cbc, analyte):
    return (
        cbc[cbc.analyte == analyte]
        .groupby("mission_day", as_index=False)["value"]
        .mean()
        .rename(columns={"mission_day": "day"})
        .dropna()
        .sort_values("day")
        .reset_index(drop=True)
    )


# --- mission-day conversion is applied BEFORE fitting -----------------------

def test_fitting_on_raw_timepoint_labels_is_rejected():
    """The guard that matters: if someone skips to_mission_day() and hands the
    models raw 'L-92' / 'R+1' labels, the fit must fail loudly.

    Modelling on label order would silently treat the 3-day flight and the
    112-day gap out to R+194 as equal steps.
    """
    raw = pd.DataFrame({
        "day": ["L-92", "L-44", "L-3", "R+1", "R+45", "R+82", "R+194"],
        "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
    })
    with pytest.raises(TypeError, match="to_mission_day"):
        check_training_frame(raw)

    for factory in MODELS.values():
        with pytest.raises(TypeError, match="to_mission_day"):
            factory().fit(raw)


def test_real_series_carries_mission_days_not_labels(cbc):
    series = series_for(cbc, SHAPED)
    assert list(series["day"]) == [-92, -44, -3, 4, 48, 85, 197]
    # R+1 must be day 4 (return is day 3), not day 1 — otherwise the flight has
    # been collapsed out of the timeline.
    assert to_mission_day("R+1") == 4
    assert 4 in set(series["day"])
    assert pd.api.types.is_numeric_dtype(series["day"])


def test_mission_phase_partitions_the_timeline():
    assert mission_phase(-92) == "preflight"
    assert mission_phase(0) == "inflight"
    assert mission_phase(3) == "inflight"
    assert mission_phase(4) == "recovery"
    assert mission_phase(197) == "recovery"


# --- all three models fit both shapes ---------------------------------------

@pytest.mark.parametrize("analyte", [SHAPED, FLAT])
@pytest.mark.parametrize("name", list(MODELS))
def test_model_fits_and_predicts(cbc, analyte, name):
    series = series_for(cbc, analyte)
    model = MODELS[name]()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(series)
        predicted = model.predict([4, 197, 227])

    assert list(predicted["day"]) == [4, 197, 227]
    assert predicted["yhat"].notna().all(), f"{name} produced NaN point predictions"
    assert np.isfinite(predicted["yhat"]).all()

    # Predictions must be in the same universe as the data, not orders out.
    # (An explosive AR once put hemoglobin at -4.7 against observations near 14.)
    low, high = series["value"].min(), series["value"].max()
    span = high - low or 1.0
    assert (predicted["yhat"] > low - 5 * span).all()
    assert (predicted["yhat"] < high + 5 * span).all()


@pytest.mark.parametrize("name", list(MODELS))
def test_uncertainty_is_real_or_nan_never_fabricated(cbc, name):
    series = series_for(cbc, FLAT)
    model = MODELS[name]()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(series)
        predicted = model.predict([197])

    if model.has_uncertainty:
        assert predicted["yhat_lower"].notna().all()
        assert predicted["yhat_upper"].notna().all()
        assert (predicted["yhat_lower"] <= predicted["yhat"]).all()
        assert (predicted["yhat"] <= predicted["yhat_upper"]).all()
    else:
        # LightGBM has no native interval. It must say so with NaN, not invent one.
        assert predicted["yhat_lower"].isna().all()
        assert predicted["yhat_upper"].isna().all()


def test_lightgbm_declares_no_uncertainty():
    assert LightGBMModel.has_uncertainty is False
    assert ProphetModel.has_uncertainty is True
    assert ArimaModel.has_uncertainty is True


# --- LOO-CV -----------------------------------------------------------------

@pytest.mark.parametrize("analyte", [SHAPED, FLAT])
def test_loo_runs_and_produces_finite_metrics(cbc, analyte):
    series = series_for(cbc, analyte)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = compare(MODELS, series)

    for name, metrics in result["models"].items():
        assert metrics["n_folds"] == 7, f"{name}: LOO should use all 7 timepoints"
        assert metrics["n_failed"] == 0, f"{name}: {metrics['n_failed']} folds failed"
        for metric in ("mae", "rmse", "mape"):
            value = metrics[metric]
            assert value is not None, f"{name}: {metric} is None"
            assert np.isfinite(value), f"{name}: {metric} is not finite"
            assert value >= 0

    assert result["best_by_mae"] in MODELS


def test_loo_holds_out_every_timepoint_exactly_once(cbc):
    series = series_for(cbc, FLAT)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        folds = leave_one_out(ProphetModel, series)

    assert sorted(folds["day"]) == sorted(series["day"])
    assert len(folds) == len(series)


def test_a_model_that_always_fails_scores_as_failed_not_as_perfect():
    """A fold that cannot fit is NaN, not dropped. Otherwise a model that only
    converges on easy folds would look better than one that converges on all."""
    class Broken(ProphetModel):
        def fit(self, df):
            raise RuntimeError("nope")

    series = pd.DataFrame({"day": [-92, -44, -3, 4, 48, 85, 197],
                           "value": [1.0, 2, 3, 4, 5, 6, 7]})
    folds = leave_one_out(Broken, series)
    metrics = score(folds)

    assert metrics["n_failed"] == 7
    assert metrics["mae"] is None  # not 0.0


def test_mape_is_not_poisoned_by_near_zero_truth():
    folds = pd.DataFrame({"day": [1, 2], "y_true": [0.0, 10.0],
                          "y_pred": [0.5, 11.0], "error": [None, None]})
    metrics = score(folds)
    assert np.isfinite(metrics["mape"])  # the y_true=0 fold is excluded, not inf


# --- what-if ----------------------------------------------------------------

def test_whatif_extrapolates_past_last_observed_day(cbc):
    series = series_for(cbc, SHAPED)
    model = ProphetModel()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(series)
        result = what_if(model, series, extra_days=30)

    assert result["last_observed_day"] == 197
    assert result["day"] == 227
    assert result["extrapolated"] is True
    assert np.isfinite(result["yhat"])
    assert result["yhat_lower"] < result["yhat"] < result["yhat_upper"]


def test_whatif_flags_lightgbm_flat_extrapolation(cbc):
    """Tree models return a boundary leaf outside their training range. That is a
    flat line, not a forecast, and the response must say so."""
    series = series_for(cbc, SHAPED)
    model = LightGBMModel()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(series)
        result = what_if(model, series, extra_days=30)

    assert result["flat_extrapolation"] is True
    assert "cannot extrapolate" in result["caveat"]
    assert result["yhat_lower"] is None  # no fabricated band
    assert result["has_uncertainty"] is False


def test_whatif_rejects_nonpositive_horizon(cbc):
    series = series_for(cbc, FLAT)
    model = ProphetModel()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(series)
    with pytest.raises(ValueError):
        what_if(model, series, extra_days=0)
