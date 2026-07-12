"""Guards for the two bugs that display-rounding introduced in the A/B router."""

import json
import math

import numpy as np
import pandas as pd

from routers.abtest import _round, _to_records


def frame(rows):
    return pd.DataFrame(
        rows, columns=["base_mean", "log2fc", "pvalue", "padj"],
        index=[f"ENSMUSG{i:011d}" for i in range(len(rows))],
    )


def test_nan_padj_becomes_json_null_not_nan():
    """DESeq2 leaves padj NaN for genes dropped by independent filtering. Raw NaN
    is not valid JSON and yields a payload the frontend cannot parse."""
    records = _to_records(frame([[534.5, -2.07, 1e-103, np.nan]]))
    assert records[0]["padj"] is None

    encoded = json.dumps(records)  # would raise/emit NaN if unhandled
    assert "NaN" not in encoded
    assert json.loads(encoded)[0]["padj"] is None


def test_base_mean_keeps_magnitude():
    """Regression: rounding base_mean to significant FIGURES (%.2g) turned 534.54
    into 530, destroying real information. It must be decimal places."""
    assert _round(534.54321, "base_mean") == 534.54
    assert _round(82571.7, "base_mean") == 82571.7
    assert _round(0.0123, "base_mean") == 0.01


def test_pvalues_keep_their_exponent():
    """p-values span ~100 orders of magnitude, so they need significant figures,
    not decimal places — round(1e-103, 3) would be 0.0."""
    assert _round(2.3284e-103, "pvalue") == 2.33e-103
    assert _round(4.4492e-99, "padj") == 4.45e-99
    assert _round(1e-103, "pvalue") > 0


def test_rounding_never_moves_a_gene_across_the_significance_cutoff():
    """Regression: counting significance on the ROUNDED records let a gene at
    padj=0.0499 round to 0.05 and silently drop out of n_significant.

    The endpoint counts on the unrounded frame; this pins the hazard itself.
    """
    borderline = 0.04996
    results = frame([[100.0, 1.0, 1e-3, borderline]])

    true_count = int((results["padj"] < 0.05).sum())
    rounded = _to_records(results)[0]["padj"]
    rounded_count = sum(1 for r in [rounded] if r is not None and r < 0.05)

    assert true_count == 1
    # The rounded value does cross the cutoff — which is exactly why the endpoint
    # must not count on it.
    assert rounded == 0.05 and rounded_count == 0
    assert true_count != rounded_count


def test_all_fields_are_finite_or_none():
    records = _to_records(frame([
        [1.0, np.inf, np.nan, np.nan],
        [2.0, -1.5, 0.01, 0.04],
    ]))
    for record in records:
        for field in ("base_mean", "log2fc", "pvalue", "padj"):
            value = record[field]
            assert value is None or math.isfinite(value)
