"""Preprocessing for count matrices headed into NB differential expression.

RSEM reports *expected* counts: a read that maps ambiguously to several isoforms
is split fractionally between them, so a gene can carry 12.7 reads. The values
are floats by nature, not by accident.

Negative-binomial DE (DESeq2 and the GLM in `rnaseq.py`) models counts as
discrete draws. Handing it floats is not a type nuisance — the NB likelihood is
defined on non-negative integers, and fractional input either errors out or
silently produces a distribution that was never fit to real data. So rounding is
a required step, not a convenience.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def round_expected_counts(counts: pd.DataFrame) -> pd.DataFrame:
    """Round RSEM expected counts to integers for NB modelling.

    Rounds half away from zero (12.5 -> 13), matching the convention DESeq2's
    own documentation recommends for RSEM input. Python's built-in `round` and
    numpy's `np.round` both use banker's rounding (12.5 -> 12, 13.5 -> 14),
    which biases a matrix where .5 values are common.

    Raises rather than coercing, because every failure mode here is silent:

    * non-numeric input -> would become NaN and drop genes without warning
    * negative values   -> not counts; the NB likelihood is undefined there
    * NaN / inf         -> would propagate into size factors and poison the fit
    """
    if not isinstance(counts, pd.DataFrame):
        raise TypeError(f"Expected a DataFrame, got {type(counts).__name__}")

    non_numeric = [
        column for column, dtype in counts.dtypes.items()
        if not pd.api.types.is_numeric_dtype(dtype)
    ]
    if non_numeric:
        raise TypeError(
            f"Non-numeric count columns: {non_numeric[:5]}. "
            "Counts must be numeric; refusing to coerce."
        )

    values = counts.to_numpy(dtype=float)

    if not np.isfinite(values).all():
        n_bad = int((~np.isfinite(values)).sum())
        raise ValueError(
            f"{n_bad} non-finite value(s) (NaN/inf) in count matrix. "
            "Refusing to round; these would poison size factors downstream."
        )

    if (values < 0).any():
        worst = float(values.min())
        raise ValueError(
            f"Negative value(s) in count matrix (min={worst}). These are not "
            "counts and the negative-binomial likelihood is undefined for them."
        )

    # Half away from zero. Values are already known non-negative, so floor(x+0.5).
    rounded = np.floor(values + 0.5).astype(np.int64)

    return pd.DataFrame(rounded, index=counts.index, columns=counts.columns)
