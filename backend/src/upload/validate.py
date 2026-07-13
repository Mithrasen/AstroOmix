"""Validation for user-uploaded data.

Everything here validates *before* any analysis runs, and every check reuses the
project's existing validators rather than restating them — `round_expected_counts`
for the numeric checks, `assign_groups` for the design, `check_training_frame` for
the time series. Their error messages are surfaced verbatim; they are not
suppressed, reinterpreted, or replaced with vaguer wording.

The memory finding that shapes this module
------------------------------------------
The obvious guardrail — cap the upload size so a DESeq2 run stays small — does
not work, because **pydeseq2's memory is almost independent of the data size**:

    30,000 genes x 50 samples   2,499 MB peak
    22,720 x 12 (OSD-104)       2,405 MB
     5,000 x 12                 2,359 MB

The cost is the joblib/loky worker pool, not the matrix. A 5,000-gene upload
costs essentially as much as the OSD-104 run that `ALLOW_REFRESH` exists to
prevent. Capping rows would have looked like a safety measure while providing
none.

So uploads are analysed with the **negative-binomial GLM** in `src/abtest/rnaseq.py`
instead, which is single-process statsmodels and stays flat:

    30,000 x 50                   219 MB
    10,000 x 12                   167 MB

That is the engine choice, and it is a real methodological difference the user is
told about — the NB GLM has unshrunk method-of-moments dispersions, so its
p-value tail is over-confident relative to DESeq2. DESeq2 on an upload remains
available, but only where `ALLOW_REFRESH=true` (i.e. not in the deployed app).
"""

from __future__ import annotations

import io

import pandas as pd

from src.abtest.preprocess import round_expected_counts
from src.abtest.rnaseq import DesignError, assign_groups
from src.forecast.common import check_training_frame

# --- caps --------------------------------------------------------------------

MAX_COUNTS_BYTES = 10 * 1024 * 1024     # 10 MB — matches the widget cap exactly
MAX_SERIES_BYTES = 1 * 1024 * 1024      # 1 MB — a two-column series is tiny
MAX_GENES = 30_000
MAX_SAMPLES = 50
MIN_TIMEPOINTS = 3                      # enforced by check_training_frame too

MAX_RUNS_PER_SESSION = 5


class UploadError(ValueError):
    """A rejected upload. The message is shown to the user verbatim."""


def _check_size(data: bytes, limit: int, what: str) -> None:
    if len(data) > limit:
        raise UploadError(
            f"{what} is {len(data) / 1024 / 1024:.1f} MB, over the "
            f"{limit / 1024 / 1024:.0f} MB hosted-demo limit. "
            "This is a limit of the hosted demo, not of the biology."
        )


def _read_csv(data: bytes, index_col) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(data), index_col=index_col)
    except Exception as error:
        raise UploadError(f"Could not parse the file as CSV: {error}") from error


# --- A/B counts --------------------------------------------------------------

def validate_counts(data: bytes) -> tuple[pd.DataFrame, pd.Series]:
    """Validate an uploaded counts CSV (genes x samples).

    Returns (rounded integer counts, group assignment). Raises UploadError with a
    message safe to show the user.
    """
    _check_size(data, MAX_COUNTS_BYTES, "The counts file")

    counts = _read_csv(data, index_col=0)

    if counts.empty or counts.shape[1] == 0:
        raise UploadError(
            "The counts file has no data columns. Expected genes as rows "
            "(first column = gene ID) and samples as columns."
        )

    if len(counts) > MAX_GENES:
        raise UploadError(
            f"{len(counts):,} genes, over the {MAX_GENES:,} limit."
        )
    if counts.shape[1] > MAX_SAMPLES:
        raise UploadError(
            f"{counts.shape[1]} samples, over the {MAX_SAMPLES} limit."
        )

    # Reuse the real validator. It rejects non-numeric columns, negatives, NaN and
    # inf — and it rounds RSEM-style fractional counts to the integers the NB model
    # requires. We surface its message rather than paraphrasing it.
    try:
        rounded = round_expected_counts(counts)
    except (TypeError, ValueError) as error:
        raise UploadError(str(error)) from error

    # Reuse the real design validator too. It requires every sample to carry a
    # _FLT_ or _GC_ token, both groups present, and >=2 replicates each.
    try:
        groups = assign_groups(rounded.columns)
    except DesignError as error:
        raise UploadError(
            f"{error}\n\nSample columns must contain `_FLT_` (flight) or `_GC_` "
            "(ground), e.g. `Mmus_SLS_FLT_Rep1_M25`."
        ) from error

    return rounded, groups


def validate_design(data: bytes, counts: pd.DataFrame) -> pd.Series:
    """Validate an optional design CSV: two columns, sample and group.

    Used when the sample names do not themselves carry _FLT_/_GC_ tokens.
    """
    _check_size(data, MAX_SERIES_BYTES, "The design file")
    design = _read_csv(data, index_col=None)

    if design.shape[1] < 2:
        raise UploadError(
            "The design file needs two columns: sample name, and group "
            "('flight' or 'ground')."
        )

    sample_column, group_column = design.columns[:2]
    mapping = dict(zip(design[sample_column].astype(str),
                       design[group_column].astype(str).str.strip().str.lower()))

    missing = [c for c in counts.columns if c not in mapping]
    if missing:
        raise UploadError(
            f"{len(missing)} sample column(s) in the counts file have no row in the "
            f"design file: {missing[:5]}"
        )

    unknown = sorted({v for v in mapping.values()} - {"flight", "ground"})
    if unknown:
        raise UploadError(
            f"Unrecognised group label(s): {unknown}. Use 'flight' or 'ground'."
        )

    groups = pd.Series({c: mapping[c] for c in counts.columns}, name="group")
    counts_by_group = groups.value_counts()

    if set(counts_by_group.index) != {"flight", "ground"}:
        raise UploadError(
            f"The design needs both groups, got: {counts_by_group.to_dict()}"
        )
    if counts_by_group.min() < 2:
        raise UploadError(
            f"Need at least 2 replicates per group, got: {counts_by_group.to_dict()}"
        )
    return groups


# --- forecasting series ------------------------------------------------------

def validate_series(data: bytes) -> tuple[pd.DataFrame, str]:
    """Validate an uploaded time series CSV: `day`, `value`, optional `group`.

    Returns (frame with columns day/value, the group column name or '').
    """
    _check_size(data, MAX_SERIES_BYTES, "The series file")

    frame = _read_csv(data, index_col=None)
    frame.columns = [str(c).strip().lower() for c in frame.columns]

    for required in ("day", "value"):
        if required not in frame.columns:
            raise UploadError(
                f"Missing a `{required}` column. Expected columns: `day`, `value`, "
                "and optionally a group/crew column. `day` must already be a "
                "numeric mission day — not a raw 'L-92'/'R+1' label."
            )

    series = frame[["day", "value"]].copy()

    # check_training_frame is the real validator: it rejects a non-numeric `day`
    # (which is how a raw 'L-92' label gets caught), drops NaN rows, and enforces
    # the >= 3 usable timepoints minimum. Surface its message as-is.
    try:
        clean = check_training_frame(series)
    except (TypeError, ValueError) as error:
        raise UploadError(str(error)) from error

    if not pd.api.types.is_numeric_dtype(clean["value"]):
        raise UploadError("`value` must be numeric.")

    return clean, ""


# --- session rate limit ------------------------------------------------------

def check_rate_limit(state, key: str) -> None:
    """Refuse more than MAX_RUNS_PER_SESSION analysis runs per session.

    An uploaded run is uncached by definition, so without a cap a single session
    could queue an unbounded amount of work on a shared free-tier container.
    """
    used = state.get(key, 0)
    if used >= MAX_RUNS_PER_SESSION:
        raise UploadError(
            f"Upload limit reached: {MAX_RUNS_PER_SESSION} analysis runs per "
            "session. Reload the page to start a new session. (Uploaded runs are "
            "uncached, so they are capped to keep the shared app responsive.)"
        )


def record_run(state, key: str) -> int:
    state[key] = state.get(key, 0) + 1
    return state[key]
