"""Mouse–human orthology from MGI, with mapping ambiguity made explicit.

The whole point of this module is that mouse→human orthology is **not a lookup
table**. It is a many-to-many bipartite graph, and collapsing it into a dict of
mouse→human would quietly throw away the ambiguity that a reader needs in order
to know how much to trust a cross-species claim.

So nothing here joins. `map_mouse_genes` returns every match *tagged with its
cardinality*, and callers decide what an ambiguous match is worth.

Cardinality is computed on the GRAPH, not per homology class
------------------------------------------------------------
This distinction is not cosmetic. MGI groups genes into homology classes, and a
per-class reading of the file says there is exactly **1** many-to-many mouse gene
in the entire mouse genome. That is an artefact: the human gene HSD3B1 appears in
three *separate* classes, paired with Hsd3b8, Hsd3b9 and Hsd3b4 respectively. Read
class by class, each looks like a tidy "one mouse → two human" mapping, and the
fact that one human gene has three mouse partners is invisible.

Building the bipartite graph across all classes and asking, per mouse gene, "do
any of my human partners also have other mouse partners?" gives the real picture:

    one_to_one     17,092
    many_to_one     1,692
    many_to_many    1,031
    one_to_many       366
    no_ortholog     1,746

1,031 vs 1. That gap is the ambiguity that a naive join silently discards.

Identifiers
-----------
Keyed internally on **MGI IDs**, which are stable. Symbols are not: the mouse
ortholog of human TP53 is `Trp53`, not `Tp53`, so a symbol-keyed lookup of "Tp53"
returns nothing and looks like a missing ortholog rather than a typo.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"
HOMOLOGY_FILE = REFERENCE_DIR / "HOM_MouseHumanSequence.rpt"
COORD_FILE = REFERENCE_DIR / "MGI_Gene_Model_Coord.rpt"

MOUSE_TAXON = "10090"
HUMAN_TAXON = "9606"

# MGI_Gene_Model_Coord.rpt declares 15 header fields but its rows carry 16 (a
# trailing tab). pandas silently shifts every column one position left, so this
# file is read POSITIONALLY. See data/reference/README.md.
COORD_MGI_ID = 0
COORD_ENSEMBL_ID = 10

CARDINALITIES = ("one_to_one", "one_to_many", "many_to_one", "many_to_many", "no_ortholog")


class OrthologyMap:
    """Bipartite mouse↔human ortholog graph, plus an ENSMUSG→MGI bridge."""

    def __init__(self, mouse_to_human, human_to_mouse, ensembl_to_mgi,
                 mgi_symbol, human_symbol):
        self.mouse_to_human = mouse_to_human      # MGI id -> {human HGNC/Entrez keys}
        self.human_to_mouse = human_to_mouse      # human key -> {MGI ids}
        self.ensembl_to_mgi = ensembl_to_mgi      # ENSMUSG -> {MGI ids}
        self.mgi_symbol = mgi_symbol              # MGI id -> mouse symbol
        self.human_symbol = human_symbol          # human key -> human symbol

    def cardinality(self, mgi_id: str) -> str:
        """Classify one mouse gene's orthology relationship."""
        humans = self.mouse_to_human.get(mgi_id, set())
        if not humans:
            return "no_ortholog"

        # Does any human partner also have other mouse partners? That is what
        # makes a mapping "many_*" — and it is invisible class-by-class.
        shared = any(len(self.human_to_mouse[h]) > 1 for h in humans)

        if len(humans) == 1:
            return "many_to_one" if shared else "one_to_one"
        return "many_to_many" if shared else "one_to_many"


def _load_homology(path: Path):
    mouse_to_human = defaultdict(set)
    human_to_mouse = defaultdict(set)
    mgi_symbol, human_symbol = {}, {}

    by_class = defaultdict(lambda: {"mouse": set(), "human": set()})

    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            taxon = row["NCBI Taxon ID"]
            key = row["DB Class Key"]
            symbol = (row["Symbol"] or "").strip()

            if taxon == MOUSE_TAXON:
                mgi = (row["Mouse MGI ID"] or "").strip()
                if not mgi:
                    continue
                # Sets, not lists: the file repeats rows for the same gene within
                # a class (Try5 twice in class 51818048), and counting those as
                # separate genes would invent orthologs that do not exist.
                by_class[key]["mouse"].add(mgi)
                mgi_symbol[mgi] = symbol

            elif taxon == HUMAN_TAXON:
                # HGNC where available, else EntrezGene — a stable key, not the symbol.
                hgnc = (row["HGNC ID"] or "").strip()
                entrez = (row["EntrezGene ID"] or "").strip()
                human = hgnc or (f"Entrez:{entrez}" if entrez else "")
                if not human:
                    continue
                by_class[key]["human"].add(human)
                human_symbol[human] = symbol

    for members in by_class.values():
        for mouse in members["mouse"]:
            for human in members["human"]:
                mouse_to_human[mouse].add(human)
                human_to_mouse[human].add(mouse)

    # Mouse genes present in the file with no human member: real "no ortholog"
    # calls, and they must exist as keys so they are reported, not dropped.
    for members in by_class.values():
        for mouse in members["mouse"]:
            mouse_to_human.setdefault(mouse, set())

    return mouse_to_human, human_to_mouse, mgi_symbol, human_symbol


def _load_ensembl_bridge(path: Path):
    ensembl_to_mgi = defaultdict(set)
    with path.open(encoding="utf-8", newline="") as handle:
        next(handle)  # header
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) <= COORD_ENSEMBL_ID:
                continue
            mgi = fields[COORD_MGI_ID].strip()
            ensembl = fields[COORD_ENSEMBL_ID].strip()

            # The file carries the literal string "null" in the Ensembl column for
            # some markers. Left in, it becomes a key named "null" that collects
            # unrelated MGI ids under one bogus gene. Require a real ENSMUSG id.
            if not mgi.startswith("MGI:") or not ensembl.startswith("ENSMUSG"):
                continue
            ensembl_to_mgi[ensembl].add(mgi)
    return ensembl_to_mgi


@lru_cache(maxsize=1)
def load_orthology() -> OrthologyMap:
    """Parse the MGI reference files. Cached — this is a ~31MB read."""
    for path in (HOMOLOGY_FILE, COORD_FILE):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing MGI reference file: {path}. See data/reference/README.md."
            )

    mouse_to_human, human_to_mouse, mgi_symbol, human_symbol = _load_homology(HOMOLOGY_FILE)
    ensembl_to_mgi = _load_ensembl_bridge(COORD_FILE)

    return OrthologyMap(mouse_to_human, human_to_mouse, ensembl_to_mgi,
                        mgi_symbol, human_symbol)


def map_mouse_genes(ensembl_ids) -> list[dict]:
    """Map mouse ENSMUSG ids to human orthologs, tagged with cardinality.

    Returns one record per input gene — **including genes with no ortholog and
    genes with no Ensembl→MGI bridge at all**. Nothing is dropped: a gene that
    silently vanishes from a cross-species table reads as "not significant"
    rather than "not mappable", which is a different and much worse claim.

    Record:
        ensembl_id, mgi_id, mouse_symbol, human_symbols, human_ids,
        cardinality, n_human, unambiguous
    """
    orthology = load_orthology()
    records = []

    for ensembl_id in ensembl_ids:
        mgi_ids = orthology.ensembl_to_mgi.get(ensembl_id, set())

        if not mgi_ids:
            records.append({
                "ensembl_id": ensembl_id,
                "mgi_id": None,
                "mouse_symbol": None,
                "human_symbols": [],
                "human_ids": [],
                "cardinality": "no_ortholog",
                "n_human": 0,
                "unambiguous": False,
                "reason": "no Ensembl->MGI mapping in MGI_Gene_Model_Coord.rpt",
            })
            continue

        # An ENSMUSG can itself bridge to more than one MGI id. Take them all
        # rather than picking one arbitrarily.
        for mgi_id in sorted(mgi_ids):
            humans = sorted(orthology.mouse_to_human.get(mgi_id, set()))
            cardinality = orthology.cardinality(mgi_id)

            records.append({
                "ensembl_id": ensembl_id,
                "mgi_id": mgi_id,
                "mouse_symbol": orthology.mgi_symbol.get(mgi_id),
                "human_symbols": [orthology.human_symbol.get(h, h) for h in humans],
                "human_ids": humans,
                "cardinality": cardinality,
                "n_human": len(humans),
                # The only category a downstream consumer may treat as a clean
                # 1:1 correspondence.
                "unambiguous": cardinality == "one_to_one",
                "reason": None if humans else "in MGI homology file, no human member",
            })

    return records


def summarise(records) -> dict:
    """Count records by cardinality."""
    counts = {c: 0 for c in CARDINALITIES}
    for record in records:
        counts[record["cardinality"]] += 1
    return counts
