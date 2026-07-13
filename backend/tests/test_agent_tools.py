"""The tools must return REAL computed output, with the caveats attached.

If a caveat is missing from a tool result, the agent cannot enforce it — it can
only enforce what it is shown. So these tests assert the warnings are present,
not merely that the numbers are.
"""

import warnings

import pytest

from routers.forecast import _build, _valid_analytes
from src.agent.tools import DISPATCH, TOOLS, get_de_results, get_forecast, list_analytes, run_tool


def test_list_analytes_returns_the_real_twenty():
    result = list_analytes()
    assert result["n_analytes"] == 20
    assert set(result["analytes"]) == set(_valid_analytes())
    assert "mean" in result["crew"]


def test_get_forecast_matches_the_real_computed_payload():
    """Every value the agent sees must be the value the app computes. If these
    diverge, the agent is reporting numbers that appear nowhere on the pages."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        truth = _build("hemoglobin", "mean", 30)

    result = get_forecast("hemoglobin", "mean", 30)

    assert result["observed"] == truth["observed"]
    assert result["comparison"]["metrics"] == truth["comparison"]["metrics"]
    assert result["comparison"]["best_by_mae"] == truth["comparison"]["best_by_mae"]
    assert result["n_timepoints"] == truth["n_timepoints"] == 7
    assert result["n_crew"] == 4


def test_forecast_carries_the_honesty_flags():
    """These are the fields the system prompt tells the agent to surface. If the
    tool strips them, the instruction is unenforceable."""
    result = get_forecast("absolute_neutrophils", "mean", extra_days=30)

    assert "best_by_mae_warning" in result["comparison"]
    assert result["comparison"]["best_by_mae"] == "lightgbm"
    assert result["comparison"]["best_by_mae_warning"], "the warning must be populated"
    assert "cannot extrapolate" in result["comparison"]["best_by_mae_warning"]

    lightgbm = result["whatif"]["lightgbm"]
    assert lightgbm["flat_extrapolation"] is True
    assert lightgbm["yhat_lower"] is None  # no fabricated band
    assert result["model_uncertainty"]["lightgbm"] is False
    assert result["model_uncertainty"]["prophet"] is True

    assert "illustrative" in result["caveat"] or "not a clinical claim" in result["caveat"]


def test_forecast_reports_the_real_last_observed_day():
    """The agent is told to reason over last_observed_day, not to assume 197."""
    result = get_forecast("hemoglobin", "mean", 0)
    assert result["last_observed_day"] == 197
    assert max(p["day"] for p in result["observed"]) == 197
    assert "R+1 is day 4" in result["mission_day_axis"]


def test_no_warning_when_a_model_with_uncertainty_wins():
    """The warning is conditional — it must not fire spuriously, or it becomes noise."""
    result = get_forecast("hemoglobin", "mean", 0)
    assert result["comparison"]["best_by_mae"] == "prophet"
    assert result["comparison"]["best_by_mae_warning"] is None


def test_unknown_analyte_returns_an_error_not_a_guess():
    result = get_forecast("unobtainium")
    assert "error" in result
    assert "valid_analytes" in result
    assert "yhat" not in result


def test_get_de_results_returns_real_deseq2_numbers():
    result = get_de_results("OSD-104", top_n=5)
    assert result["method"] == "DESeq2 (pydeseq2)"
    assert result["n_significant_fdr_0.05"] == 5483
    assert result["n_genes_tested"] == 22720
    assert len(result["top_genes_by_padj"]) == 5
    assert result["top_genes_by_padj"][0]["gene"].startswith("ENSMUSG")
    assert "n = 6 per group" in result["caveat"]


def test_unknown_accession_returns_an_error():
    result = get_de_results("OSD-999")
    assert "error" in result
    assert "top_genes_by_padj" not in result


# --- schema hygiene ----------------------------------------------------------

def test_every_declared_tool_is_dispatchable():
    declared = {t["name"] for t in TOOLS}
    assert declared == set(DISPATCH), "a declared tool with no implementation would 500"


def test_tool_failures_are_returned_as_data_not_raised():
    """The agent must be able to see and report a failure; an exception here would
    take the page down instead."""
    result = run_tool("get_forecast", {"analyte": "hemoglobin", "crew": "NOPE"})
    assert "error" in result

    assert "error" in run_tool("no_such_tool", {})


def test_forecast_tool_description_tells_the_model_to_call_it():
    """Opus 4.8 under-reaches for tools unless the description says WHEN to call."""
    forecast = next(t for t in TOOLS if t["name"] == "get_forecast")
    description = forecast["description"].lower()
    assert "never answer" in description or "call this" in description
