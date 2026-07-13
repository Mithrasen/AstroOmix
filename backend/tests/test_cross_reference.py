import warnings

import pytest

from src.integrate.cross_reference import CBC_SYSTEMS, cbc_context, cross_reference


@pytest.fixture(scope="module")
def result():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cross_reference("OSD-104", limit=200)


def test_declares_itself_not_a_statistical_integration(result):
    """The honesty contract is machine-readable, not just prose in a docstring."""
    assert result["is_statistical_integration"] is False
    joined = " ".join(result["caveats"]).lower()
    assert "not a statistical integration" in joined
    assert "skeletal muscle" in joined and "whole blood" in joined
    assert "pathway" in joined


def test_ambiguous_and_unmappable_genes_survive_into_the_table(result):
    """The cardinality counts must add up to the gene list — nothing dropped."""
    counts = result["orthology"]["cardinality"]
    assert sum(counts.values()) == len(result["genes"])
    assert result["n_genes"] == len(result["genes"])


def test_ambiguity_is_reported_not_collapsed(result):
    counts = result["orthology"]["cardinality"]
    # Real DE sets contain all of these; if any bucket is empty the classifier is
    # probably collapsing categories.
    assert counts["one_to_one"] > 0
    assert counts["no_ortholog"] > 0
    assert result["orthology"]["n_ambiguous"] == (
        counts["one_to_many"] + counts["many_to_one"] + counts["many_to_many"]
    )


def test_only_one_to_one_genes_are_marked_unambiguous(result):
    for gene in result["genes"]:
        assert gene["unambiguous"] == (gene["cardinality"] == "one_to_one")


def test_genes_keep_their_de_statistics(result):
    gene = result["genes"][0]
    for field in ("ensembl_id", "log2fc", "padj", "cardinality", "human_symbols"):
        assert field in gene
    assert gene["padj"] < 0.05


def test_cbc_context_is_labelled_as_hand_curated(result):
    note = result["cbc_context"]["note"].lower()
    assert "not a computed result" in note
    assert "no statistical link" in note


def test_every_cbc_analyte_has_a_system_annotation():
    analytes = cbc_context()
    assert len(analytes) == 20
    for entry in analytes:
        assert entry["system"] != "unannotated", entry["analyte"]
        assert entry["analyte"] in CBC_SYSTEMS
    systems = " ".join(e["system"] for e in analytes)
    assert "immune" in systems and "erythroid" in systems and "haemostasis" in systems
