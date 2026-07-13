"""Which symbols to search, and in which species.

This is the bridge between the DE results (which speak ENSMUSG) and PubMed (which
speaks gene symbols). It does not reimplement orthology — `src/integrate/orthology.py`
already builds the MGI bipartite graph, cardinality and all, and it is the only
place that mapping is allowed to happen.

The rule this module exists to enforce: a mouse symbol and its human ortholog are
searched as TWO SEPARATE QUERIES, and each result is labelled with the species of
the symbol that found it. They are never pooled. `Spp1` and `SPP1` are different
literatures about different organisms, and a paper found by the mouse symbol is
mouse-derived evidence no matter how tidy the 1:1 mapping looks.

No ortholog is a normal outcome (1,746 mouse genes in MGI have none). That gets
said out loud and the mouse symbol is searched alone — not silently skipped, and
certainly not substituted with a human symbol that does not exist.
"""

from __future__ import annotations

from src.integrate.orthology import map_mouse_genes


def resolve_symbols(gene: str) -> dict:
    """Work out which symbols to search for one gene.

    Accepts an ENSMUSG id (resolved through MGI) or a bare symbol (searched as
    given, species unknown — we do not guess a species from capitalisation).

    Returns: mouse_symbol, human_symbols, cardinality, and `targets` — the
    (symbol, species) pairs to query, each already labelled.
    """
    gene = (gene or "").strip()

    if not gene.upper().startswith("ENSMUSG"):
        # A bare symbol. We will not infer species from the shape of the string:
        # "SPP1" being upper-case is a convention, not a fact, and a wrong species
        # label is worse than an honest "unspecified".
        return {
            "input": gene,
            "input_type": "symbol",
            "mouse_symbol": None,
            "human_symbols": [],
            "ortholog_cardinality": None,
            "targets": [{"symbol": gene, "species": "unspecified"}],
            "note": (
                "Searched as a literal symbol. No ortholog mapping was performed, "
                "so results are not labelled by species."
            ),
        }

    records = map_mouse_genes([gene])
    record = records[0] if records else None

    if record is None or not record.get("mouse_symbol"):
        return {
            "input": gene,
            "input_type": "ensembl",
            "mouse_symbol": None,
            "human_symbols": [],
            "ortholog_cardinality": "no_ortholog",
            "targets": [],
            "note": (
                f"{gene} could not be resolved to a mouse symbol via MGI, so no "
                "literature query could be built. This is a mapping gap, not an "
                "absence of literature."
            ),
        }

    mouse_symbol = record["mouse_symbol"]
    human_symbols = list(record.get("human_symbols") or [])
    cardinality = record.get("cardinality")

    targets = [{"symbol": mouse_symbol, "species": "mouse"}]

    if human_symbols:
        # Every human ortholog is searched, not just the first. Picking one from a
        # one_to_many mapping would hide the ambiguity the orthology module exists
        # to expose.
        for symbol in human_symbols:
            targets.append({"symbol": symbol, "species": "human"})
        note = (
            f"{mouse_symbol} (mouse) maps to {', '.join(human_symbols)} (human) with "
            f"cardinality {cardinality}. The mouse and human symbols are searched "
            "SEPARATELY and the results are labelled by the species of the symbol "
            "that retrieved them."
        )
        if cardinality != "one_to_one":
            note += (
                f" This mapping is {cardinality}, i.e. ambiguous — the human "
                "literature retrieved may concern a paralog rather than the direct "
                "counterpart of the mouse gene."
            )
    else:
        note = (
            f"{mouse_symbol} has NO human ortholog in MGI. Only the mouse symbol "
            "was searched, and every result is mouse-derived. There is no human "
            "evidence here to report."
        )

    return {
        "input": gene,
        "input_type": "ensembl",
        "mgi_id": record.get("mgi_id"),
        "mouse_symbol": mouse_symbol,
        "human_symbols": human_symbols,
        "ortholog_cardinality": cardinality,
        "targets": targets,
        "note": note,
    }
