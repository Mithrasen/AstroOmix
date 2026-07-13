"""Orthology tests.

The two that matter most: many-to-many cases must be TAGGED, not silently
collapsed; and genes with no ortholog must be REPORTED, not dropped.
"""

import pytest

from src.integrate.orthology import (
    CARDINALITIES,
    load_orthology,
    map_mouse_genes,
    summarise,
)


@pytest.fixture(scope="module")
def orthology():
    return load_orthology()


def ensembl_for(orthology, symbol):
    """Find an ENSMUSG for a mouse symbol (tests are written against symbols,
    but the code keys on stable MGI ids)."""
    mgi_ids = {m for m, s in orthology.mgi_symbol.items() if s == symbol}
    for ensembl, mgis in orthology.ensembl_to_mgi.items():
        if mgis & mgi_ids:
            return ensembl
    raise AssertionError(f"no ENSMUSG found for {symbol}")


# --- the reference files parsed at all ---------------------------------------

def test_reference_files_parse(orthology):
    assert len(orthology.mouse_to_human) > 20000
    assert len(orthology.human_to_mouse) > 15000
    # The Ensembl bridge is the piece that silently broke when read with a naive
    # pd.read_csv (15 header fields, 16 data fields -> every column shifted).
    assert len(orthology.ensembl_to_mgi) > 50000


def test_ensembl_bridge_is_not_column_shifted(orthology):
    """Regression: a shifted parse yields keys that are chromosome numbers, not
    ENSMUSG ids, and the whole mapping matches nothing while raising no error."""
    keys = list(orthology.ensembl_to_mgi)[:200]
    assert all(k.startswith("ENSMUSG") for k in keys), keys[:5]
    values = orthology.ensembl_to_mgi[keys[0]]
    assert all(v.startswith("MGI:") for v in values)


# --- known real ortholog pairs -----------------------------------------------

@pytest.mark.parametrize(
    "mouse_symbol,human_symbol",
    [
        ("Actb", "ACTB"),
        ("Myod1", "MYOD1"),
        ("Trp53", "TP53"),   # NB: mouse p53 is Trp53, NOT Tp53
        ("Alb", "ALB"),
    ],
)
def test_known_one_to_one_pairs(orthology, mouse_symbol, human_symbol):
    ensembl = ensembl_for(orthology, mouse_symbol)
    [record] = [r for r in map_mouse_genes([ensembl]) if r["mouse_symbol"] == mouse_symbol]

    assert human_symbol in record["human_symbols"]
    assert record["cardinality"] == "one_to_one"
    assert record["unambiguous"] is True
    assert record["n_human"] == 1


def test_mouse_symbol_is_not_the_human_symbol(orthology):
    """Trp53 vs Tp53 — symbol-keyed lookups are a trap; we key on MGI ids."""
    assert not any(s == "Tp53" for s in orthology.mgi_symbol.values())
    assert any(s == "Trp53" for s in orthology.mgi_symbol.values())


# --- MANY-TO-MANY IS TAGGED, NOT COLLAPSED ----------------------------------

def test_known_many_to_many_is_tagged(orthology):
    """Gstm1 -> {GSTM1, GSTM5}, and GSTM1 also has other mouse partners.

    A naive join would emit one row and lose both facts.
    """
    ensembl = ensembl_for(orthology, "Gstm1")
    [record] = [r for r in map_mouse_genes([ensembl]) if r["mouse_symbol"] == "Gstm1"]

    assert record["cardinality"] == "many_to_many"
    assert record["unambiguous"] is False
    assert record["n_human"] > 1
    assert len(record["human_symbols"]) > 1

    # The defining property: at least one human partner is shared with another
    # mouse gene. This is what a per-class reading of the MGI file misses.
    shared = [h for h in record["human_ids"] if len(orthology.human_to_mouse[h]) > 1]
    assert shared, "many_to_many requires a human partner with multiple mouse genes"


def test_hsd3b_family_many_to_many_spans_homology_classes(orthology):
    """MGI splits Hsd3b8 / Hsd3b9 / Hsd3b4 into SEPARATE homology classes, each
    pairing with HSD3B1/HSD3B2. Read class-by-class, each looks like a tidy
    one_to_many and the shared human partner is invisible.

    Graph-wide, HSD3B1 has several mouse partners — so these are many_to_many.
    """
    hsd3b1 = [h for h, s in orthology.human_symbol.items() if s == "HSD3B1"]
    assert hsd3b1
    partners = orthology.human_to_mouse[hsd3b1[0]]
    assert len(partners) > 1, "HSD3B1 should have multiple mouse partners"

    ensembl = ensembl_for(orthology, "Hsd3b8")
    [record] = [r for r in map_mouse_genes([ensembl]) if r["mouse_symbol"] == "Hsd3b8"]
    assert record["cardinality"] == "many_to_many"
    assert record["unambiguous"] is False


def test_one_to_many_and_many_to_one_are_distinguished(orthology):
    """These are different failure modes and must not be merged into one 'ambiguous'
    bucket: one_to_many splits a mouse gene across human genes; many_to_one means
    several mouse genes collapse onto the same human gene."""
    all_cards = {
        orthology.cardinality(mgi) for mgi in list(orthology.mouse_to_human)[:5000]
    }
    assert "one_to_one" in all_cards
    assert {"one_to_many", "many_to_one", "many_to_many"} & all_cards


def test_the_graph_finds_far_more_ambiguity_than_per_class_reading(orthology):
    """Sanity check on the whole point of the module: graph-wide cardinality must
    surface >>1 many_to_many gene. A per-class reading of MGI finds exactly 1."""
    cards = [orthology.cardinality(m) for m in orthology.mouse_to_human]
    n_mm = cards.count("many_to_many")
    assert n_mm > 100, f"expected many many_to_many genes graph-wide, got {n_mm}"


# --- NO-ORTHOLOG GENES ARE REPORTED, NOT DROPPED ----------------------------

def test_gene_with_no_ortholog_is_reported_not_dropped(orthology):
    """A gene that vanishes from a cross-species table reads as 'not significant'
    rather than 'not mappable'. Those are very different claims."""
    no_ortholog_mgi = next(
        m for m, humans in orthology.mouse_to_human.items() if not humans
    )
    ensembl = next(
        e for e, mgis in orthology.ensembl_to_mgi.items() if no_ortholog_mgi in mgis
    )

    records = map_mouse_genes([ensembl])
    assert records, "no-ortholog gene was dropped entirely"

    record = next(r for r in records if r["mgi_id"] == no_ortholog_mgi)
    assert record["cardinality"] == "no_ortholog"
    assert record["human_symbols"] == []
    assert record["unambiguous"] is False
    assert record["reason"]


def test_unknown_ensembl_id_is_reported_not_dropped():
    records = map_mouse_genes(["ENSMUSG99999999999"])
    assert len(records) == 1
    assert records[0]["cardinality"] == "no_ortholog"
    assert records[0]["mgi_id"] is None
    assert "no Ensembl->MGI mapping" in records[0]["reason"]


def test_every_input_gene_appears_in_the_output(orthology):
    """The invariant that makes the table trustworthy: nothing is silently lost."""
    inputs = [
        ensembl_for(orthology, "Actb"),
        ensembl_for(orthology, "Gstm1"),
        "ENSMUSG99999999999",
    ]
    records = map_mouse_genes(inputs)
    assert set(inputs) == {r["ensembl_id"] for r in records}


def test_summarise_counts_every_record():
    records = map_mouse_genes(["ENSMUSG99999999999"])
    counts = summarise(records)
    assert set(counts) == set(CARDINALITIES)
    assert sum(counts.values()) == len(records)
