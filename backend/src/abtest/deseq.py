"""DESeq2 differential expression: spaceflight vs. ground control.

This is the real thing — pydeseq2, the Python port of DESeq2 — and it is what
the `/api/abtest/{accession}` endpoint serves.

Why this exists alongside `rnaseq.py`
-------------------------------------
`rnaseq.py` is a hand-rolled negative-binomial GLM. It is kept as a tested
internal cross-check (it caught two real dispersion bugs), but it is NOT DESeq2:
its dispersions are unshrunk method-of-moments estimates, so its p-value tail
runs to implausible extremes (~1e-118 at n=6 per group). DESeq2 shrinks per-gene
dispersions toward a fitted mean-dispersion trend (empirical Bayes), which is
what makes small-n inference trustworthy.

Do not point the API at `rnaseq.py`. The two are expected to agree on *ranking*
and disagree on the extremity of small p-values; that is the whole point.

Output schema
-------------
pydeseq2 emits `baseMean` / `log2FoldChange` / `pvalue` / `padj`. We rename to
`base_mean` / `log2fc` / `pvalue` / `padj` so the schema matches what the rest of
the project (and the frontend) already expects.
"""

from __future__ import annotations

import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

from src.abtest.preprocess import round_expected_counts
from src.abtest.rnaseq import assign_groups
from src.data.loaders import fetch_counts

# DESeq2's own recommendation for a minimal pre-filter: drop genes with almost no
# information. It does independent filtering internally too, but this keeps the
# fit fast and the multiple-testing burden honest.
MIN_TOTAL_COUNT = 10


def run_deseq2(accession: str, min_total_count: int = MIN_TOTAL_COUNT,
               quiet: bool = True) -> pd.DataFrame:
    """Run DESeq2 flight-vs-ground on an OSD accession.

    Returns a table indexed by gene, sorted by padj, with columns:
        base_mean, log2fc, pvalue, padj

    Rounding is applied unconditionally: RSEM emits fractional expected counts
    and DESeq2's NB model requires integers.
    """
    counts = round_expected_counts(fetch_counts(accession))
    groups = assign_groups(counts.columns)

    keep = counts.sum(axis=1) >= min_total_count
    counts = counts.loc[keep]
    if counts.empty:
        raise ValueError(
            f"No gene in {accession} reached min_total_count={min_total_count}."
        )

    # pydeseq2 wants samples as rows, genes as columns.
    metadata = pd.DataFrame({"group": groups.loc[counts.columns]},
                            index=counts.columns)

    dds = DeseqDataSet(
        counts=counts.T,
        metadata=metadata,
        design="~group",
        refit_cooks=True,
        quiet=quiet,
    )
    dds.deseq2()

    # Contrast is flight over ground, so a positive log2fc means up in flight.
    stats = DeseqStats(dds, contrast=["group", "flight", "ground"], quiet=quiet)
    stats.summary()

    results = stats.results_df.rename(columns={
        "baseMean": "base_mean",
        "log2FoldChange": "log2fc",
    })
    results.index.name = "gene"
    return results[["base_mean", "log2fc", "pvalue", "padj"]].sort_values(
        ["padj", "pvalue"]
    )
