"""GET /api/integrate/{rodent_accession} — rodent DE genes with human ortholog status.

This endpoint serves an **evidence table**, not a statistical integration. The
response says so in `is_statistical_integration: false` and in `caveats`, and
those fields are not decoration — the rodent data is mouse skeletal muscle and the
human data is whole blood, so no correlation between them would mean anything.
See src/integrate/cross_reference.py.
"""

from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException, Query

from routers.studies import load_studies
from src.data.loaders import CACHE_DIR
from src.integrate.cross_reference import cross_reference

router = APIRouter(prefix="/api/integrate", tags=["integrate"])

INTEGRATE_CACHE = CACHE_DIR / "integrate"


def _abtest_accessions() -> set[str]:
    return {s["accession"] for s in load_studies() if s["module"] == "abtest"}


def _clean(value):
    """NaN is not valid JSON. DESeq2 leaves NaN padj/pvalue on filtered genes."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sanitise(payload: dict) -> dict:
    for gene in payload["genes"]:
        for key, value in list(gene.items()):
            gene[key] = _clean(value)
    return payload


@router.get("/{accession}")
def integrate(
    accession: str,
    fdr: float = Query(0.05, gt=0, le=1, description="FDR cutoff for DE significance."),
    limit: int = Query(500, ge=1, le=5000,
                       description="Cap on genes returned, ranked by FDR."),
    refresh: bool = Query(False),
) -> dict:
    allowed = _abtest_accessions()
    if accession not in allowed:
        raise HTTPException(
            status_code=404,
            detail=f"{accession!r} is not a rodent A/B dataset. Available: {sorted(allowed)}",
        )

    path = INTEGRATE_CACHE / f"{accession}__fdr{fdr}__limit{limit}.json"
    if path.is_file() and not refresh:
        return json.loads(path.read_text())

    payload = _sanitise(cross_reference(accession, fdr=fdr, limit=limit))

    # The cardinality summary counts ALL significant genes; `limit` only caps the
    # gene list that is returned. Say so, rather than letting the two numbers
    # disagree silently.
    payload["truncated"] = payload["n_genes"] >= limit
    if payload["truncated"]:
        payload["truncation_note"] = (
            f"Gene list capped at {limit}, ranked by FDR. The orthology counts "
            "describe exactly the genes returned."
        )

    INTEGRATE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload
