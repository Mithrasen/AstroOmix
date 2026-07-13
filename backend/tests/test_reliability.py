"""Graduated honesty by sample size.

A hard floor at 3 points is not enough. 3 points is *fittable*, not trustworthy —
and the models will draw a confident-looking curve on it. These tests pin the
graduation so it cannot silently regress into "you uploaded 4 points, here's a
forecast".
"""

import warnings

import pandas as pd
import pytest

from src.forecast.reliability import (
    CRITICAL,
    ROUTINE,
    THIN,
    assess,
)
from src.upload.analyse import run_forecast
from src.upload.validate import UploadError, validate_series

DAYS = [-92, -44, -3, 4, 48, 85, 197, 240, 280, 320, 360, 400]
VALUES = [2707, 3994, 4845, 3657, 3300, 3515, 3466, 3400, 3380, 3410, 3390, 3395]


def series_csv(n: int) -> bytes:
    return pd.DataFrame(
        {"day": DAYS[:n], "value": VALUES[:n]}
    ).to_csv(index=False).encode()


def run(n: int) -> dict:
    series, _ = validate_series(series_csv(n))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_forecast(series, extra_days=30)


# --- below the floor: hard error --------------------------------------------

@pytest.mark.parametrize("n", [1, 2])
def test_below_three_points_is_rejected_outright(n):
    with pytest.raises(UploadError, match="[Nn]eed >=3"):
        validate_series(series_csv(n))


def test_an_empty_series_is_rejected_too():
    """An empty CSV trips the dtype guard before the count guard — a different
    message, but still a hard rejection. Pinned so it cannot become a silent pass."""
    with pytest.raises(UploadError):
        validate_series(series_csv(0))


# --- n=3: fittable, but NOTHING is validated --------------------------------

def test_n3_runs_but_no_model_is_validated():
    """The trap: at n=3 every LOO fold trains on 2 points — below the fit floor —
    so every fold fails and there is no score at all. That is not 'a weak result',
    it is 'no result', and the two must not look alike."""
    payload = run(3)
    metrics = payload["comparison"]["metrics"]

    assert all(m["mae"] is None for m in metrics.values())
    assert all(m["n_failed"] == m["n_folds"] == 3 for m in metrics.values())
    assert payload["comparison"]["best_by_mae"] is None

    grade = assess(payload["n_timepoints"], metrics)
    assert grade["tier"] == CRITICAL
    assert grade["forecasting_recommended"] is False
    assert grade["loo_validated"] is False
    assert "not supported at 3 timepoints" in grade["headline"]
    assert any("No model could be validated" in r for r in grade["reasons"])


def test_n3_still_emits_a_forecast_which_is_exactly_why_the_warning_is_needed():
    """The models DO produce a curve and a what-if at n=3. The warning is the only
    thing standing between that curve and a reader who believes it."""
    payload = run(3)
    assert payload["whatif"]["prophet"]["yhat"] is not None
    assert assess(3, payload["comparison"]["metrics"])["tier"] == CRITICAL


def test_thin_data_produces_a_NARROWER_band_which_is_backwards():
    """The counter-intuitive fact the warning exists to state: fewer points means
    less residual variance, so the interval gets TIGHTER on WEAKER evidence."""
    def width(n):
        w = run(n)["whatif"]["prophet"]
        return w["yhat_upper"] - w["yhat_lower"]

    narrow, wide = width(3), width(7)
    assert narrow < wide, "if this ever flips, rewrite the warning — do not delete it"

    grade = assess(3, run(3)["comparison"]["metrics"])
    assert any("NARROWER" in r for r in grade["reasons"])


# --- n=4-5: validated, but not trustworthy ----------------------------------

@pytest.mark.parametrize("n", [4, 5])
def test_four_and_five_points_run_but_are_flagged_untrustworthy(n):
    payload = run(n)
    metrics = payload["comparison"]["metrics"]

    # These DO validate — every fold fits — which is precisely the danger: the
    # numbers look real.
    assert any(m["mae"] is not None for m in metrics.values())
    assert payload["comparison"]["best_by_mae"] is not None

    grade = assess(n, metrics)
    assert grade["tier"] == CRITICAL
    assert grade["forecasting_recommended"] is False
    assert grade["loo_validated"] is True
    assert "too few for a trustworthy forecast" in grade["headline"]
    assert any("NARROWER" in r for r in grade["reasons"])


# --- n=6-9: thin (the CBC regime) -------------------------------------------

def test_seven_points_is_thin_not_critical():
    """n=7 is the Inspiration4 CBC panel. It must land in the same tier as the
    caveat the app already makes about it — illustrative, not a claim."""
    grade = assess(7, run(7)["comparison"]["metrics"])
    assert grade["tier"] == THIN
    assert grade["forecasting_recommended"] is False
    assert "thin" in grade["headline"]
    assert any("Inspiration4 CBC" in r for r in grade["reasons"])


def test_the_cbc_page_lands_in_the_thin_tier_too():
    """The real CBC payload — not a synthetic one — must be graded, so the graduated
    warning is one system and not a special case bolted onto uploads."""
    from routers.forecast import _build

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        payload = _build("hemoglobin", "mean", 30)

    grade = assess(payload["n_timepoints"], payload["comparison"]["metrics"])
    assert payload["n_timepoints"] == 7
    assert grade["tier"] == THIN


# --- n>=10: routine ---------------------------------------------------------

def test_ten_or_more_points_is_routine():
    grade = assess(12, run(12)["comparison"]["metrics"])
    assert grade["tier"] == ROUTINE
    assert grade["forecasting_recommended"] is True
    assert any("does not validate the what-if" in r for r in grade["reasons"])


# --- the tiers are ordered and total ----------------------------------------

def test_no_sample_size_falls_through_ungraded():
    for n in range(3, 30):
        grade = assess(n, {"prophet": {"mae": 1.0}})
        assert grade["tier"] in {CRITICAL, THIN, ROUTINE}
        assert isinstance(grade["reasons"], list) and grade["reasons"]


def test_all_none_metrics_force_critical_at_any_n():
    """Even at a comfortable n, if every fold failed there is no evidence — the
    grade must not be softened by the sample size alone."""
    grade = assess(20, {"prophet": {"mae": None}, "arima": {"mae": None}})
    assert grade["tier"] == CRITICAL
    assert grade["loo_validated"] is False
