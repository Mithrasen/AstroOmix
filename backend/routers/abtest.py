"""GET /api/abtest/{accession} — DESeq2 flight-vs-ground differential expression.

Backed by `src.abtest.deseq.run_deseq2` (real pydeseq2), NOT by the hand-rolled
NB GLM in `rnaseq.py`. See that module's docstring for why the distinction
matters.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from routers.studies import load_studies
from src.abtest.deseq import run_deseq2
from src.data.loaders import CACHE_DIR

router = APIRouter(prefix="/api/abtest", tags=["abtest"])

DE_CACHE = CACHE_DIR / "de"


def _abtest_accessions() -> set[str]:
    """Only accessions declared as A/B datasets may be run.

    An unbounded accession parameter would let any caller trigger an arbitrary
    archive download plus a full DESeq2 fit — slow, and on a free-tier dyno,
    effectively a denial of service.
    """
    return {s["accession"] for s in load_studies() if s["module"] == "abtest"}


def _cached_results(accession: str, refresh: bool = False) -> pd.DataFrame:
    """Run DESeq2, or return the cached table. DESeq2 takes ~15s per accession,
    which is far too slow to repeat on every page load."""
    DE_CACHE.mkdir(parents=True, exist_ok=True)
    path = DE_CACHE / f"{accession}__deseq2.csv"

    if path.is_file() and not refresh:
        return pd.read_csv(path, index_col=0)

    results = run_deseq2(accession)
    results.to_csv(path)
    return results


# Full float64 repr costs ~17 digits per value and roughly doubles the payload for
# precision that no plot or table can show. Trim it — but note the two units are
# different: base_mean and log2fc are rounded to DECIMAL PLACES, while p-values
# span ~100 orders of magnitude and must be rounded to SIGNIFICANT FIGURES.
# (Using significant figures on base_mean would turn 534.5 into 530.)
DECIMALS = {"base_mean": 2, "log2fc": 4}
SIGFIGS = {"pvalue": 3, "padj": 3}


def _round(value: float, field: str) -> float:
    if field in DECIMALS:
        return round(value, DECIMALS[field])
    return float(f"{value:.{SIGFIGS[field]}g}")


def _to_records(results: pd.DataFrame) -> list[dict]:
    """Serialise to JSON-safe records.

    DESeq2 leaves `padj` as NaN for genes dropped by independent filtering, and
    `pvalue` as NaN for genes zeroed by Cooks outlier refitting. NaN is NOT valid
    JSON — emitting it produces a payload the frontend cannot parse — so it must
    become null explicitly.
    """
    records = []
    for gene, row in results.iterrows():
        record = {"gene": str(gene)}
        for field in ("base_mean", "log2fc", "pvalue", "padj"):
            value = row[field]
            record[field] = None if value is None or (
                isinstance(value, float) and not math.isfinite(value)
            ) else _round(float(value), field)
        records.append(record)
    return records


@router.get("/{accession}")
def abtest(
    accession: str,
    refresh: bool = Query(False, description="Bypass the cache and re-run DESeq2."),
) -> dict:
    """Flight-vs-ground DESeq2 results for one rodent accession.

    Returns every tested gene — the volcano plot needs the full cloud, not just
    the significant hits.
    """
    allowed = _abtest_accessions()
    if accession not in allowed:
        raise HTTPException(
            status_code=404,
            detail=f"{accession!r} is not an A/B dataset. Available: {sorted(allowed)}",
        )

    results = _cached_results(accession, refresh=refresh)

    # Count significance on the UNROUNDED table. Counting it on the serialised
    # records lets display rounding change the science: a gene at padj 0.0499
    # rounds to 0.05 and silently drops out of the count.
    significant = int((results["padj"] < 0.05).sum())

    records = _to_records(results)

    return {
        "accession": accession,
        "method": "DESeq2 (pydeseq2)",
        "contrast": "flight vs ground",
        "n_genes": len(records),
        "n_significant": significant,
        "results": records,
    }
