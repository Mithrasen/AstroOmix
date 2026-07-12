import numpy as np
import pandas as pd
import pytest

from src.abtest.preprocess import round_expected_counts


def frame(values):
    return pd.DataFrame(values, index=["g1", "g2"], columns=["s1", "s2"])


# --- (a) rounding behaviour on known inputs ---------------------------------

def test_rounds_to_nearest_integer():
    out = round_expected_counts(frame([[12.4, 12.6], [0.2, 99.8]]))
    assert out.values.tolist() == [[12, 13], [0, 100]]


def test_rounds_half_away_from_zero_not_bankers():
    """np.round(12.5) == 12 and np.round(13.5) == 14 (banker's rounding), which
    biases matrices where .5 is common. We want 13 and 14."""
    out = round_expected_counts(frame([[12.5, 13.5], [0.5, 1.5]]))
    assert out.values.tolist() == [[13, 14], [1, 2]]
    assert np.round(12.5) == 12  # documents the behaviour we are avoiding


def test_exact_integers_are_unchanged():
    out = round_expected_counts(frame([[0.0, 7.0], [1205.0, 0.0]]))
    assert out.values.tolist() == [[0, 7], [1205, 0]]


def test_returns_integer_dtype_preserving_labels():
    original = frame([[1.2, 3.4], [5.6, 7.8]])
    out = round_expected_counts(original)
    assert all(pd.api.types.is_integer_dtype(d) for d in out.dtypes)
    assert list(out.index) == list(original.index)
    assert list(out.columns) == list(original.columns)
    assert original.dtypes.eq(float).all()  # input not mutated


# --- (b) fails loudly rather than silently coercing --------------------------

def test_negative_counts_raise():
    with pytest.raises(ValueError, match="[Nn]egative"):
        round_expected_counts(frame([[1.0, -0.4], [2.0, 3.0]]))


def test_small_negative_raises_rather_than_rounding_to_zero():
    """-0.4 would floor(x+0.5) to 0 and vanish. It must not."""
    with pytest.raises(ValueError):
        round_expected_counts(frame([[-0.4, 1.0], [2.0, 3.0]]))


def test_non_numeric_column_raises():
    df = pd.DataFrame({"s1": [1.0, 2.0], "s2": ["12.5", "oops"]}, index=["g1", "g2"])
    with pytest.raises(TypeError, match="[Nn]on-numeric"):
        round_expected_counts(df)


def test_nan_raises():
    with pytest.raises(ValueError, match="non-finite"):
        round_expected_counts(frame([[1.0, np.nan], [2.0, 3.0]]))


def test_inf_raises():
    with pytest.raises(ValueError, match="non-finite"):
        round_expected_counts(frame([[1.0, np.inf], [2.0, 3.0]]))


def test_non_dataframe_raises():
    with pytest.raises(TypeError):
        round_expected_counts([[1.0, 2.0]])
