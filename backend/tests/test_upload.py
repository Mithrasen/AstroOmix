"""Upload validation and guardrails.

The guardrail that actually matters is NOT the size cap. pydeseq2's memory is
almost independent of the matrix — 5,000x12 peaks at 2,359 MB against 2,499 MB
for 30,000x50 — because the cost is its worker pool. So capping rows would have
looked like a memory guard while being none. Uploads run the single-process NB
GLM instead (~220 MB at the cap); DESeq2 stays gated behind ALLOW_REFRESH.
"""

import numpy as np
import pandas as pd
import pytest

from src.upload.analyse import ENGINES, run_de, run_forecast
from src.upload.validate import (
    MAX_GENES,
    MAX_RUNS_PER_SESSION,
    MAX_SAMPLES,
    UploadError,
    check_rate_limit,
    record_run,
    validate_counts,
    validate_design,
    validate_series,
)

RNG = np.random.default_rng(7)


def counts_csv(n_genes=200, n_samples=8, de_genes=40, lfc=2.0) -> bytes:
    half = n_samples // 2
    cols = ([f"Mmus_X_FLT_Rep{i}" for i in range(half)]
            + [f"Mmus_X_GC_Rep{i}" for i in range(n_samples - half)])
    base = RNG.uniform(50, 400, n_genes)
    effect = np.ones(n_genes)
    effect[:de_genes] = 2.0 ** lfc
    data = np.zeros((n_genes, n_samples))
    for j, column in enumerate(cols):
        mu = base * (effect if "_FLT_" in column else 1.0)
        data[:, j] = RNG.negative_binomial(20, 20 / (20 + mu))
    frame = pd.DataFrame(data, index=[f"G{i}" for i in range(n_genes)], columns=cols)
    return frame.to_csv().encode()


def series_csv(days=(-92, -44, -3, 4, 48, 85, 197)) -> bytes:
    values = [2707, 3994, 4845, 3657, 3300, 3515, 3466][: len(days)]
    return pd.DataFrame({"day": list(days), "value": values}).to_csv(index=False).encode()


# --- valid uploads -----------------------------------------------------------

def test_valid_counts_upload_validates_and_runs():
    counts, groups = validate_counts(counts_csv())
    assert (groups == "flight").sum() == 4
    assert (groups == "ground").sum() == 4
    assert all(pd.api.types.is_integer_dtype(d) for d in counts.dtypes)

    results = run_de(counts, engine="nb_glm")
    assert {"base_mean", "log2fc", "pvalue", "padj"} <= set(results.columns)
    assert results["padj"].notna().any()
    # The truly-DE genes should surface.
    significant = set(results[results["padj"] < 0.05].index)
    recovered = len(significant & {f"G{i}" for i in range(40)}) / 40
    assert recovered > 0.5, f"only recovered {recovered:.0%} of known DE genes"


def test_valid_series_upload_validates_and_runs():
    series, _ = validate_series(series_csv())
    assert list(series["day"]) == [-92, -44, -3, 4, 48, 85, 197]

    payload = run_forecast(series, extra_days=30)
    assert payload["n_timepoints"] == 7
    assert set(payload["curves"]) == {"prophet", "arima", "lightgbm"}
    assert payload["comparison"]["best_by_mae"] in {"prophet", "arima", "lightgbm"}
    assert payload["whatif"]["lightgbm"]["flat_extrapolation"] is True


# --- size and shape caps -----------------------------------------------------

def test_oversized_counts_file_is_rejected():
    blob = b"x" * (7 * 1024 * 1024)   # over the 6 MB hosted-demo cap
    with pytest.raises(UploadError, match="over the .* MB hosted-demo limit"):
        validate_counts(blob)


def test_too_many_genes_rejected():
    frame = pd.DataFrame(
        RNG.integers(0, 9, (MAX_GENES + 1, 4)),
        index=[f"G{i}" for i in range(MAX_GENES + 1)],
        columns=["A_FLT_1", "B_FLT_2", "C_GC_1", "D_GC_2"],
    )
    with pytest.raises(UploadError, match="over the .* limit"):
        validate_counts(frame.to_csv().encode())


def test_too_many_samples_rejected():
    n = MAX_SAMPLES + 1
    cols = [f"S{i}_FLT" if i < n // 2 else f"S{i}_GC" for i in range(n)]
    frame = pd.DataFrame(RNG.integers(0, 9, (10, n)),
                         index=[f"G{i}" for i in range(10)], columns=cols)
    with pytest.raises(UploadError, match="samples, over the"):
        validate_counts(frame.to_csv().encode())


def test_oversized_series_rejected():
    with pytest.raises(UploadError, match="over the"):
        validate_series(b"day,value\n" + b"1,2\n" * 300_000)   # >1 MB


# --- malformed data: the EXISTING validators do the rejecting ---------------

def test_non_numeric_counts_rejected_by_round_expected_counts():
    frame = pd.DataFrame({"S1_FLT_a": ["x", "y"], "S2_GC_b": ["1", "2"]},
                         index=["G1", "G2"])
    with pytest.raises(UploadError, match="[Nn]on-numeric"):
        validate_counts(frame.to_csv().encode())


def test_negative_counts_rejected_by_round_expected_counts():
    frame = pd.DataFrame(RNG.integers(0, 50, (10, 4)).astype(float),
                         index=[f"G{i}" for i in range(10)],
                         columns=["A_FLT_1", "B_FLT_2", "C_GC_1", "D_GC_2"])
    frame.iloc[0, 0] = -5.0
    with pytest.raises(UploadError, match="[Nn]egative"):
        validate_counts(frame.to_csv().encode())


def test_missing_group_tokens_rejected_by_assign_groups():
    frame = pd.DataFrame(RNG.integers(0, 50, (10, 4)).astype(float),
                         index=[f"G{i}" for i in range(10)],
                         columns=["a", "b", "c", "d"])
    with pytest.raises(UploadError, match="neither flight"):
        validate_counts(frame.to_csv().encode())


def test_unparseable_file_rejected():
    with pytest.raises(UploadError, match="Could not parse|no data columns"):
        validate_counts(b"\x00\x01\x02 not a csv at all")


def test_series_with_raw_timepoint_labels_is_rejected():
    """The existing check_training_frame guard: a raw 'L-92' label must not be
    modelled, because label order collapses the flight out of the timeline."""
    frame = pd.DataFrame({"day": ["L-92", "L-44", "L-3", "R+1"], "value": [1, 2, 3, 4]})
    with pytest.raises(UploadError, match="to_mission_day"):
        validate_series(frame.to_csv(index=False).encode())


def test_series_with_too_few_timepoints_rejected():
    with pytest.raises(UploadError, match="[Nn]eed >=3"):
        validate_series(series_csv(days=(1, 2)))


def test_series_missing_required_column_rejected():
    frame = pd.DataFrame({"time": [1, 2, 3], "value": [1, 2, 3]})
    with pytest.raises(UploadError, match="Missing a `day` column"):
        validate_series(frame.to_csv(index=False).encode())


# --- design CSV --------------------------------------------------------------

def test_design_csv_supplies_groups_when_names_lack_tokens():
    frame = pd.DataFrame(RNG.integers(1, 50, (20, 4)).astype(float),
                         index=[f"G{i}" for i in range(20)],
                         columns=["s1", "s2", "s3", "s4"])
    design = pd.DataFrame({"sample": ["s1", "s2", "s3", "s4"],
                           "group": ["flight", "flight", "ground", "ground"]})
    # The counts alone fail (no tokens) — that is the existing validator working.
    with pytest.raises(UploadError):
        validate_counts(frame.to_csv().encode())

    groups = validate_design(design.to_csv(index=False).encode(), frame)
    assert list(groups) == ["flight", "flight", "ground", "ground"]


def test_design_with_unknown_label_rejected():
    frame = pd.DataFrame(RNG.integers(1, 50, (5, 2)).astype(float),
                         index=["G1", "G2", "G3", "G4", "G5"], columns=["s1", "s2"])
    design = pd.DataFrame({"sample": ["s1", "s2"], "group": ["flight", "spaceship"]})
    with pytest.raises(UploadError, match="Unrecognised group"):
        validate_design(design.to_csv(index=False).encode(), frame)


# --- rate limit --------------------------------------------------------------

def test_sixth_run_in_a_session_is_blocked():
    state = {}
    for i in range(MAX_RUNS_PER_SESSION):
        check_rate_limit(state, "ab_runs")     # must not raise
        record_run(state, "ab_runs")
    assert state["ab_runs"] == MAX_RUNS_PER_SESSION == 5

    with pytest.raises(UploadError, match="Upload limit reached"):
        check_rate_limit(state, "ab_runs")


def test_rate_limits_are_independent_per_page():
    state = {}
    for _ in range(MAX_RUNS_PER_SESSION):
        record_run(state, "ab_runs")
    with pytest.raises(UploadError):
        check_rate_limit(state, "ab_runs")
    check_rate_limit(state, "fc_runs")   # the forecast budget is untouched


# --- engine gating -----------------------------------------------------------

def test_deseq2_engine_requires_allow_refresh():
    """The whole point: DESeq2 costs ~2.4 GB no matter how small the upload, so it
    must not be reachable in the deployed app."""
    assert ENGINES["deseq2"]["requires_allow_refresh"] is True
    assert ENGINES["nb_glm"]["requires_allow_refresh"] is False


def test_nb_glm_engine_note_does_not_claim_to_be_deseq2():
    note = ENGINES["nb_glm"]["note"]
    assert "NOT DESeq2" in note
    assert "unshrunk" in note or "over-confident" in note
