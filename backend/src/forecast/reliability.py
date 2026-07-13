"""How much to trust a forecast, given how many points it was fitted to.

A hard floor is not enough. `check_training_frame` refuses fewer than 3 points,
but 3 points is not "fine" — it is merely *fittable*. Left at a hard floor, the app
would happily render a confident-looking curve on 3 points, which is exactly the
over-reading this project exists to prevent.

Two facts, measured on this pipeline, drive the tiers below.

**At n=3 nothing is validated.** Leave-one-out holds out one point and fits on the
rest — with 3 points that leaves 2, below the fit minimum, so *every fold fails*.
The metrics come back `None` and `best_by_mae` is `None`. The models still produce
a curve and a what-if, but not one number in the comparison table is evidence that
any of them describes the data.

**The uncertainty band gets NARROWER as the data gets thinner.** Measured on the
same series, Prophet's 95% interval at the what-if point:

    n = 3   width   245
    n = 4   width  2005
    n = 7   width  2474

Fewer points means less residual variance to estimate from, so the model looks
*more* confident on *less* evidence. Every reader's intuition runs the other way.
That inversion has to be said out loud, or a thin upload reads as a precise one.
"""

from __future__ import annotations

MIN_FITTABLE = 3      # check_training_frame's floor — below this, nothing runs.
MIN_VALIDATABLE = 4   # below this, every LOO fold fails and nothing is validated.
MIN_TRUSTWORTHY = 6   # below this, forecasting is not recommended at all.
MIN_ROUTINE = 10      # at or above this, the ordinary caveats suffice.

CRITICAL = "critical"   # runs, but the forecast is not trustworthy — say so loudly
THIN = "thin"           # usable, illustrative only (the CBC n=7 case)
ROUTINE = "routine"     # ordinary caveats


def assess(n_timepoints: int, metrics: dict | None = None) -> dict:
    """Grade a forecast by its sample size. Returns a block the UI renders.

    `metrics` is the LOO comparison table, used to detect the case where every
    fold failed — that is not "a weak score", it is *no score at all*, and the two
    must not look alike.
    """
    validated = _any_model_validated(metrics)

    if n_timepoints < MIN_VALIDATABLE or not validated:
        return {
            "tier": CRITICAL,
            "forecasting_recommended": False,
            "loo_validated": validated,
            "headline": (
                f"Forecasting is not supported at {n_timepoints} timepoints. "
                "Treat everything below as illustrative only."
            ),
            "reasons": _critical_reasons(n_timepoints, validated),
        }

    if n_timepoints < MIN_TRUSTWORTHY:
        return {
            "tier": CRITICAL,
            "forecasting_recommended": False,
            "loo_validated": True,
            "headline": (
                f"{n_timepoints} timepoints is too few for a trustworthy forecast. "
                "The models below will fit, but do not rely on them."
            ),
            "reasons": [
                f"With {n_timepoints} points, each leave-one-out fold trains on "
                f"{n_timepoints - 1}. A score computed from that many points is "
                "itself extremely noisy — it is not evidence the model works.",
                NARROW_BAND_WARNING,
                "Any extrapolation past the last point is unsupported at this n.",
            ],
        }

    if n_timepoints < MIN_ROUTINE:
        return {
            "tier": THIN,
            "forecasting_recommended": False,
            "loo_validated": True,
            "headline": (
                f"{n_timepoints} timepoints — thin. This demonstrates methodology; "
                "it is not a basis for a claim."
            ),
            "reasons": [
                "This is the regime the Inspiration4 CBC panel sits in (7 "
                "timepoints). The models run, the scores are computable, and none "
                "of it is enough to assert what a marker will do next.",
                "LOO-CV measures interpolation of the observed points. It does not "
                "validate the what-if extrapolation.",
            ],
        }

    return {
        "tier": ROUTINE,
        "forecasting_recommended": True,
        "loo_validated": True,
        "headline": f"{n_timepoints} timepoints.",
        "reasons": [
            "LOO-CV measures interpolation of the observed points. It does not "
            "validate the what-if extrapolation.",
        ],
    }


NARROW_BAND_WARNING = (
    "**The uncertainty bands get NARROWER with less data, not wider.** Fewer points "
    "means less residual variance to estimate from, so a model fitted to 3 points "
    "draws a *tighter* interval than the same model fitted to 7 (measured: width 245 "
    "vs 2474). A narrow band here is a symptom of thin data, not of a confident "
    "forecast. Read it the opposite way round to your instinct."
)


def _any_model_validated(metrics: dict | None) -> bool:
    """True if at least one model produced a real LOO score.

    All-None metrics mean every fold failed — no model was validated. That is a
    different thing from a bad score and must not be rendered as one.
    """
    if not metrics:
        return False
    return any(m.get("mae") is not None for m in metrics.values())


def _critical_reasons(n_timepoints: int, validated: bool) -> list[str]:
    reasons = []
    if not validated:
        reasons.append(
            "**No model could be validated.** Leave-one-out holds out one point and "
            f"fits on the rest — with {n_timepoints} points that leaves "
            f"{n_timepoints - 1}, below the {MIN_FITTABLE}-point minimum, so *every "
            "fold failed*. The comparison table has no scores because there are "
            "none: nothing here is evidence that any of these models describes your "
            "data."
        )
    reasons.append(NARROW_BAND_WARNING)
    reasons.append(
        "The curve and the what-if below are what the models emit, not what the "
        "data supports. Do not read them as a forecast."
    )
    return reasons
