"""Evidence-linking layer between the rodent A/B module and the human I4 module.

READ THIS FIRST: what this module does NOT do
---------------------------------------------
It does not compute a statistical association between rodent DE genes and human
CBC trajectories. It cannot, and neither can anything else in this project,
because the two datasets do not share an axis on which a correlation would mean
anything:

* **Different species.** Mouse vs human — hence the orthology layer, which is
  many-to-many and lossy (see orthology.py).
* **Different tissue.** OSD-104/105 are mouse **skeletal muscle** (soleus,
  tibialis anterior). The I4 CBC panel is human **whole blood**. A muscle
  transcript and a blood cell count are not measurements of the same system.
  This is the single biggest reason not to over-read anything here.
* **Different missions and durations.** Rodent Research 1 flew ~30+ days;
  Inspiration4 flew 3 days.
* **Different measurement types.** Gene expression (counts) vs clinical cell
  counts. A DE gene is not a CBC analyte, and there is no row on which to join.

So what is produced is an **evidence table**, not an integration: which rodent DE
genes have human orthologs, how ambiguous each mapping is, and — separately —
plain-language context on which physiological system each CBC analyte tracks. The
two are presented side by side for a human to reason about. No number in this
module asserts that a rodent gene explains a human trajectory.

Pathway assignment is deliberately absent. There is no gene-set database in this
project (no MSigDB/Enrichr/GO), so any "pathway" label would be invented. Adding
real enrichment would mean adding a real gene-set source; until then the module
says nothing about pathways rather than guessing.
"""

from __future__ import annotations

import pandas as pd

from src.abtest.deseq import run_deseq2
from src.data.loaders import fetch_i4_cbc
from src.integrate.orthology import map_mouse_genes, summarise

FDR_CUTOFF = 0.05

# Hand-curated domain annotation: which physiological system each CBC analyte
# reports on. This is textbook haematology, written by hand — it is NOT derived
# from the data, and it is labelled as such in the API response so nobody mistakes
# it for a computed result.
CBC_SYSTEMS = {
    "absolute_neutrophils": "immune — innate; first responders, rise with stress and acute inflammation",
    "neutrophils": "immune — innate (percent of white cells)",
    "absolute_lymphocytes": "immune — adaptive; T/B cells",
    "lymphocytes": "immune — adaptive (percent of white cells)",
    "absolute_monocytes": "immune — innate; tissue macrophage precursors",
    "monocytes": "immune — innate (percent of white cells)",
    "absolute_eosinophils": "immune — allergic and antiparasitic response",
    "eosinophils": "immune — allergic response (percent of white cells)",
    "absolute_basophils": "immune — histamine response",
    "basophils": "immune — histamine response (percent of white cells)",
    "white_blood_cell_count": "immune — total leukocytes",
    "red_blood_cell_count": "erythroid — oxygen transport",
    "hemoglobin": "erythroid — oxygen-carrying capacity",
    "hematocrit": "erythroid — packed red cell volume; also tracks plasma volume shifts",
    "mcv": "erythroid — mean red cell volume",
    "mch": "erythroid — mean haemoglobin per red cell",
    "mchc": "erythroid — mean haemoglobin concentration",
    "rdw": "erythroid — variability in red cell size",
    "platelet_count": "haemostasis — clotting",
    "mpv": "haemostasis — mean platelet volume",
}

CAVEATS = [
    "This is an evidence-linking layer, NOT a statistical integration. No "
    "correlation, enrichment, or hypothesis test connects the rodent genes to the "
    "human analytes.",
    "Different tissue: the rodent DE is skeletal muscle (soleus / tibialis "
    "anterior); the human CBC panel is whole blood. These are not measurements of "
    "the same system.",
    "Different species: mouse-human orthology is many-to-many and lossy. Only "
    "'one_to_one' matches are unambiguous.",
    "Different missions: Rodent Research 1 flew ~30+ days; Inspiration4 flew 3 days.",
    "Pathway assignment is not performed — this project has no gene-set database, "
    "and inventing pathway labels would be fabrication.",
]


def rodent_ortholog_table(accession: str, fdr: float = FDR_CUTOFF,
                          limit: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Significant DE genes from a rodent accession, with human ortholog status.

    Genes are returned even when they have no ortholog. Dropping them would make
    an unmappable gene look like a non-significant one.
    """
    results = run_deseq2(accession)
    significant = results[results["padj"] < fdr].copy()

    if limit is not None:
        significant = significant.head(limit)

    records = map_mouse_genes(list(significant.index))
    orthologs = pd.DataFrame(records).set_index("ensembl_id")

    merged = significant.join(orthologs, how="left")
    merged.index.name = "ensembl_id"

    return merged.reset_index(), summarise(records)


def cbc_context() -> list[dict]:
    """The CBC analytes, with the physiological system each tracks."""
    cbc = fetch_i4_cbc()
    context = []
    for analyte in sorted(cbc["analyte"].unique()):
        subset = cbc[cbc.analyte == analyte]
        context.append({
            "analyte": analyte,
            "unit": str(subset["unit"].iloc[0]),
            "system": CBC_SYSTEMS.get(analyte, "unannotated"),
            "n_timepoints": int(subset["mission_day"].nunique()),
        })
    return context


def cross_reference(accession: str, fdr: float = FDR_CUTOFF,
                    limit: int | None = 500) -> dict:
    """Assemble the evidence table for one rodent accession."""
    table, cardinality = rodent_ortholog_table(accession, fdr=fdr, limit=limit)

    total = len(table)
    unambiguous = int(table["unambiguous"].sum()) if total else 0
    ambiguous = cardinality["one_to_many"] + cardinality["many_to_one"] + cardinality["many_to_many"]

    return {
        "accession": accession,
        "fdr_cutoff": fdr,
        "n_genes": total,
        "orthology": {
            "cardinality": cardinality,
            "n_unambiguous": unambiguous,
            "n_ambiguous": ambiguous,
            "n_no_ortholog": cardinality["no_ortholog"],
            "note": (
                "Only 'one_to_one' genes have an unambiguous human counterpart. "
                f"{ambiguous} gene(s) map ambiguously and {cardinality['no_ortholog']} "
                "have no human ortholog at all — none of these were dropped."
            ),
            "source": "MGI HOM_MouseHumanSequence.rpt + MGI_Gene_Model_Coord.rpt",
        },
        "genes": table.to_dict(orient="records"),
        "cbc_context": {
            "analytes": cbc_context(),
            "note": (
                "Hand-curated haematology annotation, not a computed result. Shown "
                "alongside the rodent genes for a human to reason about — no "
                "statistical link is asserted between them."
            ),
        },
        "is_statistical_integration": False,
        "caveats": CAVEATS,
    }
