"""Negative-binomial differential expression: spaceflight vs. ground control.

Applied to the GeneLab Rodent Research rodent A/B datasets (OSD-104 soleus,
OSD-105 tibialis anterior), each 6 flight vs. 6 ground.

Method
------
Per gene, a negative-binomial GLM of counts on group, with a log offset for
library size:

    counts_ij ~ NB(mu_ij, alpha_i),  log(mu_ij) = beta0_i + beta1_i * flight_j
                                                  + log(s_j)

`s_j` are median-of-ratios size factors (Anders & Huber 2010), the same
normalisation DESeq2 uses. `beta1` is the log fold change of flight over ground;
we report it in log2 and test it with a Wald test, then control FDR across genes
with Benjamini-Hochberg.

What this is NOT
----------------
Dispersion (`alpha_i`) is estimated per gene by method of moments, and then used
as-is. DESeq2 additionally shrinks per-gene dispersions toward a fitted
mean-dispersion trend (empirical Bayes). That shrinkage matters at n=6 per
group: method-of-moments dispersions are noisy on small samples, and a gene
whose within-group variance is low *by chance* gets an under-estimated alpha and
so an over-confident p-value. Our smallest adjusted p-values (~1e-118 on
OSD-104) are implausibly extreme for 6-vs-6 and are a symptom of exactly this.

So the ranking is trustworthy; the extreme tail of the p-value scale is not.
Fold changes are also unshrunk, so a low-count gene can post a large, unreliable
log2FC — filter on `base_mean` before believing one.

Treat the output as a ranked screen, not as DESeq2-equivalent output. For exact
DESeq2 semantics, run pydeseq2 over the same rounded matrix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from src.abtest.preprocess import round_expected_counts
from src.data.loaders import fetch_counts

FLIGHT_TOKEN = "_FLT_"
GROUND_TOKEN = "_GC_"


class DesignError(ValueError):
    """The sample columns do not form a usable flight-vs-ground design."""


def assign_groups(columns) -> pd.Series:
    """Label each sample 'flight' or 'ground' from its GeneLab sample name.

    GeneLab names look like `Mmus_C57-6J_SLS_FLT_Rep1_M25`. Anything that is
    neither FLT nor GC is an error: silently dropping a sample would quietly
    change the design.
    """
    groups = {}
    for column in columns:
        if FLIGHT_TOKEN in column:
            groups[column] = "flight"
        elif GROUND_TOKEN in column:
            groups[column] = "ground"
        else:
            raise DesignError(
                f"Sample {column!r} is neither flight ({FLIGHT_TOKEN}) nor "
                f"ground ({GROUND_TOKEN}); cannot assign it to a group."
            )

    series = pd.Series(groups, name="group")
    counts = series.value_counts()
    if set(counts.index) != {"flight", "ground"}:
        raise DesignError(f"Design needs both groups, got: {counts.to_dict()}")
    if counts.min() < 2:
        raise DesignError(f"Need >=2 replicates per group, got: {counts.to_dict()}")
    return series


def size_factors(counts: pd.DataFrame) -> pd.Series:
    """Median-of-ratios size factors (Anders & Huber 2010).

    Uses the geometric mean across samples as a per-gene reference, so genes with
    a zero in any sample are excluded from the reference — that is the intended
    behaviour, not an oversight.
    """
    values = counts.to_numpy(dtype=float)
    with np.errstate(divide="ignore"):
        log_counts = np.log(values)

    # Genes with a zero anywhere have a -inf log; drop them from the reference.
    reference = log_counts.mean(axis=1)
    usable = np.isfinite(reference)
    if not usable.any():
        raise ValueError(
            "No gene is non-zero across all samples; cannot compute size factors."
        )

    ratios = log_counts[usable] - reference[usable, None]
    factors = np.exp(np.median(ratios, axis=0))
    return pd.Series(factors, index=counts.columns, name="size_factor")


def filter_low_counts(counts: pd.DataFrame, min_count: int = 10,
                      min_samples: int = 3) -> pd.DataFrame:
    """Drop genes too sparse to fit. Reduces multiple-testing burden and avoids
    fitting an NB to a row of zeros."""
    keep = (counts >= min_count).sum(axis=1) >= min_samples
    return counts.loc[keep]


MIN_DISPERSION = 1e-4


def estimate_dispersions(counts: pd.DataFrame, groups: pd.Series,
                         factors: pd.Series) -> np.ndarray:
    """Method-of-moments dispersion, per gene: var = mu + alpha * mu^2.

    Two details here are load-bearing, and getting either wrong makes the whole
    test conservative enough to erase real signal:

    1. Estimate on SIZE-FACTOR-NORMALISED counts, not raw. The GLM already
       carries library size as a log offset. If dispersion is taken from raw
       counts, the spread in library sizes is absorbed into alpha a second time.
       On OSD-105 (size factors spanning 1.36x) that inflated alpha by 1.73x.

    2. Use WITHIN-GROUP variance, not total. Total variance across all samples
       includes the flight-vs-ground difference — the very effect being tested.
       A gene that truly responds to flight would inflate its own dispersion and
       so suppress its own significance.

    Together these two errors drove OSD-105 to zero significant genes when a
    plain t-test on the same matrix found 667.
    """
    normalized = counts.to_numpy(dtype=float) / factors.to_numpy(dtype=float)
    is_flight = (groups.loc[counts.columns] == "flight").to_numpy()

    flight, ground = normalized[:, is_flight], normalized[:, ~is_flight]
    n_flight, n_ground = flight.shape[1], ground.shape[1]

    pooled_variance = (
        (n_flight - 1) * flight.var(axis=1, ddof=1)
        + (n_ground - 1) * ground.var(axis=1, ddof=1)
    ) / (n_flight + n_ground - 2)

    mean = normalized.mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        alpha = (pooled_variance - mean) / (mean ** 2)

    # Under-dispersed genes (variance below Poisson) get the floor rather than a
    # negative alpha, which is not a valid NB.
    alpha = np.where(np.isfinite(alpha), alpha, MIN_DISPERSION)
    return np.clip(alpha, MIN_DISPERSION, 1e3)


def _fit_gene(y: np.ndarray, design: np.ndarray, offset: np.ndarray,
              alpha: float) -> tuple:
    """Fit one gene. Returns (log2fc, pvalue) or NaNs if the fit fails."""
    if y.mean() <= 0:
        return np.nan, np.nan

    try:
        result = sm.GLM(
            y, design,
            family=sm.families.NegativeBinomial(alpha=alpha),
            offset=offset,
        ).fit()
    except Exception:
        return np.nan, np.nan

    beta, pvalue = result.params[1], result.pvalues[1]
    if not np.isfinite(beta) or not np.isfinite(pvalue):
        return np.nan, np.nan

    return beta / np.log(2), pvalue


def differential_expression(counts: pd.DataFrame, min_count: int = 10,
                            min_samples: int = 3) -> pd.DataFrame:
    """Flight vs. ground NB differential expression on a raw counts matrix.

    Rounding via `round_expected_counts` is applied here, unconditionally — the
    RSEM matrices are floats and the NB likelihood is defined on integers, so
    this is not a caller-toggleable step.

    Returns a table indexed by gene, sorted by FDR, with columns:
        base_mean, log2fc, pvalue, padj, dispersion, n_flight, n_ground
    """
    counts = round_expected_counts(counts)  # required, not optional
    groups = assign_groups(counts.columns)

    counts = filter_low_counts(counts, min_count=min_count, min_samples=min_samples)
    if counts.empty:
        raise ValueError(
            f"No gene passed the expression filter "
            f"(min_count={min_count}, min_samples={min_samples})."
        )

    factors = size_factors(counts)
    offset = np.log(factors.to_numpy(dtype=float))

    is_flight = (groups.loc[counts.columns] == "flight").to_numpy(dtype=float)
    design = sm.add_constant(is_flight, has_constant="add")

    values = counts.to_numpy(dtype=float)
    normalized = values / factors.to_numpy(dtype=float)
    dispersion = estimate_dispersions(counts, groups, factors)

    fits = [_fit_gene(values[i], design, offset, dispersion[i])
            for i in range(values.shape[0])]
    log2fc, pvalue = (np.array(column) for column in zip(*fits))

    results = pd.DataFrame({
        "base_mean": normalized.mean(axis=1),
        "log2fc": log2fc,
        "pvalue": pvalue,
        "dispersion": dispersion,
    }, index=counts.index)

    # BH over genes that actually produced a p-value; failures stay NaN rather
    # than being treated as p=1, which would distort the FDR denominator.
    results["padj"] = np.nan
    tested = results["pvalue"].notna()
    if tested.any():
        _, padj, _, _ = multipletests(results.loc[tested, "pvalue"], method="fdr_bh")
        results.loc[tested, "padj"] = padj

    results["n_flight"] = int((groups == "flight").sum())
    results["n_ground"] = int((groups == "ground").sum())

    ordered = ["base_mean", "log2fc", "pvalue", "padj", "dispersion",
               "n_flight", "n_ground"]
    return results[ordered].sort_values(["padj", "pvalue"])


def run(accession: str, **kwargs) -> pd.DataFrame:
    """Fetch an OSD accession and run flight-vs-ground DE on it."""
    return differential_expression(fetch_counts(accession), **kwargs)
