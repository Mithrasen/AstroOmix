import numpy as np
import pandas as pd
import pytest

from src.abtest.rnaseq import (
    DesignError,
    assign_groups,
    differential_expression,
    estimate_dispersions,
    size_factors,
)

RNG = np.random.default_rng(0)


def make_counts(n_genes=300, n_per_group=6, n_de=30, lfc=2.5, library_skew=None):
    """Simulate NB counts with a known set of truly-DE genes."""
    flight = [f"Mmus_C57-6J_SLS_FLT_Rep{i+1}_M{i+1}" for i in range(n_per_group)]
    ground = [f"Mmus_C57-6J_SLS_GC_Rep{i+1}_M{i+20}" for i in range(n_per_group)]
    columns = ground + flight

    base = RNG.uniform(50, 500, size=n_genes)
    effect = np.ones(n_genes)
    effect[:n_de] = 2.0 ** lfc  # first n_de genes are up in flight

    libs = np.ones(len(columns))
    if library_skew is not None:
        libs = np.linspace(1 / library_skew, library_skew, len(columns))

    data = np.zeros((n_genes, len(columns)))
    for j, column in enumerate(columns):
        mu = base * (effect if column in flight else 1.0) * libs[j]
        data[:, j] = RNG.negative_binomial(n=1 / 0.05, p=(1 / 0.05) / ((1 / 0.05) + mu))

    genes = [f"g{i}" for i in range(n_genes)]
    return pd.DataFrame(data, index=genes, columns=columns).astype(float), genes[:n_de]


# --- design -----------------------------------------------------------------

def test_assign_groups_reads_geneLab_names():
    counts, _ = make_counts(n_genes=5)
    groups = assign_groups(counts.columns)
    assert (groups == "flight").sum() == 6
    assert (groups == "ground").sum() == 6


def test_unlabelled_sample_raises_rather_than_being_dropped():
    with pytest.raises(DesignError, match="neither flight"):
        assign_groups(["Mmus_SLS_FLT_Rep1_M1", "Mmus_SLS_GC_Rep1_M2", "Mmus_SLS_XX_Rep1_M3"])


def test_single_group_raises():
    with pytest.raises(DesignError):
        assign_groups(["a_FLT_1", "b_FLT_2"])


# --- size factors -----------------------------------------------------------

def test_size_factors_track_library_size():
    counts, _ = make_counts(n_genes=400, library_skew=2.0)
    factors = size_factors(counts)
    totals = counts.sum()
    assert np.corrcoef(factors, totals)[0, 1] > 0.95


# --- dispersion (regression test for the bug that erased all signal) --------

def test_dispersion_is_not_inflated_by_the_group_effect():
    """Regression: estimating dispersion from TOTAL variance folds the
    flight-vs-ground effect into alpha, so a strongly-DE gene inflates its own
    dispersion and suppresses its own significance. Within-group variance must
    not do that.

    Truly-DE genes should get dispersions comparable to null genes.
    """
    counts, de_genes = make_counts(n_genes=300, n_de=30, lfc=3.0)
    groups = assign_groups(counts.columns)
    alpha = pd.Series(
        estimate_dispersions(counts, groups, size_factors(counts)), index=counts.index
    )

    de_alpha = alpha.loc[de_genes].median()
    null_alpha = alpha.drop(de_genes).median()
    assert de_alpha < null_alpha * 2, (
        f"DE genes have inflated dispersion ({de_alpha:.4f} vs {null_alpha:.4f}) — "
        "the group effect is leaking into the dispersion estimate."
    )


def test_dispersion_is_not_inflated_by_library_size():
    """Regression: estimating dispersion from RAW counts double-counts library
    size, which the GLM already handles via its offset. Skewed libraries must not
    inflate alpha."""
    even, _ = make_counts(n_genes=300, n_de=0, library_skew=None)
    skewed, _ = make_counts(n_genes=300, n_de=0, library_skew=2.5)

    a_even = np.median(estimate_dispersions(even, assign_groups(even.columns),
                                            size_factors(even)))
    a_skew = np.median(estimate_dispersions(skewed, assign_groups(skewed.columns),
                                            size_factors(skewed)))
    assert a_skew < a_even * 2, (
        f"library skew inflated dispersion ({a_skew:.4f} vs {a_even:.4f})"
    )


# --- end to end -------------------------------------------------------------

def test_recovers_known_de_genes():
    counts, de_genes = make_counts(n_genes=300, n_de=30, lfc=2.5)
    results = differential_expression(counts, min_count=5, min_samples=3)

    called = set(results[results.padj < 0.05].index)
    recovered = len(called & set(de_genes)) / len(de_genes)
    assert recovered > 0.8, f"only recovered {recovered:.0%} of known DE genes"


def test_log2fc_sign_and_magnitude_are_right():
    counts, de_genes = make_counts(n_genes=300, n_de=30, lfc=2.5)
    results = differential_expression(counts, min_count=5, min_samples=3)
    observed = results.loc[de_genes, "log2fc"].median()
    assert 2.0 < observed < 3.0, f"expected log2fc ~2.5, got {observed:.2f}"


def test_null_genes_are_not_mostly_called():
    """False-discovery sanity: with no true effect, few genes should pass BH."""
    counts, _ = make_counts(n_genes=400, n_de=0)
    results = differential_expression(counts, min_count=5, min_samples=3)
    called = (results.padj < 0.05).sum()
    assert called < 0.05 * len(results), f"{called}/{len(results)} null genes called"


def test_rounding_is_applied_and_not_optional():
    """Float RSEM input must be accepted and rounded internally; a negative must
    still blow up, proving round_expected_counts is genuinely in the path."""
    counts, _ = make_counts(n_genes=100, n_de=10)
    counts += 0.4  # make it unambiguously float
    differential_expression(counts, min_count=5, min_samples=3)

    counts.iloc[0, 0] = -1.0
    with pytest.raises(ValueError, match="[Nn]egative"):
        differential_expression(counts, min_count=5, min_samples=3)


def test_results_table_shape_and_fdr_monotonicity():
    counts, _ = make_counts(n_genes=200, n_de=20)
    results = differential_expression(counts, min_count=5, min_samples=3)

    assert list(results.columns) == ["base_mean", "log2fc", "pvalue", "padj",
                                     "dispersion", "n_flight", "n_ground"]
    assert (results.n_flight == 6).all() and (results.n_ground == 6).all()
    tested = results.dropna(subset=["padj"])
    assert (tested.padj >= tested.pvalue - 1e-12).all(), "padj must be >= raw p"
    assert tested.padj.is_monotonic_increasing or tested.padj.equals(
        tested.padj.sort_values()
    )
