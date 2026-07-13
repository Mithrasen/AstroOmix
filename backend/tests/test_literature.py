"""Literature retrieval: it must be real, honest, species-correct, and fail well.

The tests that matter here are the negative ones. Retrieval working is easy; the
product claim is about what happens when it DOESN'T — when NCBI is down, when
nothing is found, when the model invents a citation. Each of those is a test.

No test in this file hits the network. NCBI is stubbed, because a suite that
depends on someone else's uptime is a suite that goes red for reasons that have
nothing to do with our code.
"""

from __future__ import annotations

import json

import pytest
import requests

from src.agent.grounding import (
    LITERATURE_TOOLS,
    cited_pmids,
    numbers_available,
    pmids_available,
    verify,
)
from src.agent.tools import search_literature_tool
from src.literature import pubmed
from src.literature.pubmed import LiteratureUnavailable, build_query, search_literature


class Call:
    """Stands in for agent.ToolCall."""

    def __init__(self, name, arguments, result):
        self.name, self.arguments, self.result = name, arguments, result


# --- fake NCBI ---------------------------------------------------------------

ESEARCH = {"esearchresult": {"idlist": ["38412345", "31234567"]}}

EFETCH = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation>
    <PMID>38412345</PMID>
    <Article>
      <Journal><Title>npj Microgravity</Title>
        <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
      </Journal>
      <ArticleTitle>Spp1 expression in <i>hindlimb</i> unloaded mice</ArticleTitle>
      <Abstract>
        <AbstractText Label="METHODS">We unloaded 24 mice (p &lt; 0.001).</AbstractText>
        <AbstractText Label="RESULTS">Spp1 was elevated 3.7-fold.</AbstractText>
      </Abstract>
      <PublicationTypeList>
        <PublicationType>Journal Article</PublicationType>
      </PublicationTypeList>
    </Article>
  </MedlineCitation></PubmedArticle>
  <PubmedArticle><MedlineCitation>
    <PMID>31234567</PMID>
    <Article>
      <Journal><Title>Bone</Title>
        <JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue>
      </Journal>
      <ArticleTitle>Osteopontin in microgravity: a review</ArticleTitle>
      <Abstract><AbstractText>Review of osteopontin literature.</AbstractText></Abstract>
      <PublicationTypeList>
        <PublicationType>Review</PublicationType>
      </PublicationTypeList>
    </Article>
  </MedlineCitation></PubmedArticle>
</PubmedArticleSet>
"""


class FakeResponse:
    def __init__(self, *, json_body=None, text="", status=200):
        self._json, self.text, self.status_code = json_body, text, status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _fresh_budget():
    pubmed.reset_session_budget()
    yield
    pubmed.reset_session_budget()


@pytest.fixture
def ncbi(monkeypatch, tmp_path):
    """A working NCBI, and a cache that does not leak between tests."""
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "literature")
    monkeypatch.setattr(pubmed, "MIN_INTERVAL_SECONDS", 0)   # no real sleeping

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        if "esearch" in url:
            return FakeResponse(json_body=ESEARCH)
        return FakeResponse(text=EFETCH)

    monkeypatch.setattr(pubmed.requests, "get", fake_get)
    return calls


# --- retrieval is real, and transcribed rather than invented -----------------

def test_records_are_transcribed_verbatim(ncbi):
    result = search_literature("Spp1", species="mouse")

    assert result["n_retrieved"] == 2
    first = result["papers"][0]

    assert first["pmid"] == "38412345"
    assert first["journal"] == "npj Microgravity"
    assert first["year"] == 2023
    assert first["url"] == "https://pubmed.ncbi.nlm.nih.gov/38412345/"
    # Inline markup must not truncate the title at the first tag.
    assert first["title"] == "Spp1 expression in hindlimb unloaded mice"
    # Both labelled abstract sections survive; taking the first would drop RESULTS.
    assert "METHODS:" in first["abstract"] and "RESULTS:" in first["abstract"]
    assert first["is_review"] is False

    assert result["papers"][1]["is_review"] is True   # metadata, not a guess


def test_query_pairs_gene_with_space_context(ncbi):
    query = build_query("Spp1")
    assert "(Spp1)" in query
    assert "microgravity" in query and "spaceflight" in query

    search_literature("Spp1", species="mouse")
    assert "(Spp1) AND (" in ncbi[0]["term"]


def test_ncbi_is_told_who_we_are(ncbi):
    search_literature("Spp1", species="mouse")
    assert ncbi[0]["tool"] == "AstroOmix"
    assert "email" in ncbi[0]


def test_results_are_cached(ncbi, monkeypatch):
    search_literature("Spp1", species="mouse")
    before = len(ncbi)
    search_literature("Spp1", species="mouse")
    assert len(ncbi) == before        # served from disk, NCBI not hit again


# --- zero results are honest, not padded -------------------------------------

def test_no_results_returns_nothing_rather_than_padding(monkeypatch, tmp_path):
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "lit")
    monkeypatch.setattr(pubmed, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(
        pubmed.requests, "get",
        lambda url, params=None, timeout=None: FakeResponse(
            json_body={"esearchresult": {"idlist": []}}
        ),
    )

    result = search_literature("Xyzzy1", species="mouse")

    assert result["n_retrieved"] == 0
    assert result["papers"] == []     # no filler, no loosely-related substitutes


# --- graceful failure ---------------------------------------------------------

def test_ncbi_outage_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "lit")
    monkeypatch.setattr(pubmed, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(pubmed, "MAX_RETRIES", 2)

    def dead(url, params=None, timeout=None):
        raise requests.ConnectionError("NCBI is down")

    monkeypatch.setattr(pubmed.requests, "get", dead)
    monkeypatch.setattr(pubmed, "time", pubmed.time)   # keep real time module

    with pytest.raises(LiteratureUnavailable):
        search_literature("Spp1", species="mouse")


def test_tool_reports_outage_instead_of_raising(monkeypatch, tmp_path):
    """The page must keep working when PubMed does not."""
    monkeypatch.setattr(pubmed, "CACHE_DIR", tmp_path / "lit")
    monkeypatch.setattr(pubmed, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(pubmed, "MAX_RETRIES", 1)
    monkeypatch.setattr(
        pubmed.requests, "get",
        lambda url, params=None, timeout=None: (_ for _ in ()).throw(
            requests.Timeout("timed out")
        ),
    )

    result = search_literature_tool("Spp1")

    assert result["literature_unavailable"] is True
    assert result["total_retrieved"] == 0
    assert result["searches"] == []
    assert "temporarily unavailable" in result["note"]
    assert "do NOT state a PMID" in result["note"].replace("Do NOT", "do NOT")


def test_session_budget_is_a_circuit_breaker(ncbi, monkeypatch):
    # The budget counts HTTP requests, not searches: one search is an esearch plus
    # an efetch. Two requests buys exactly one search.
    monkeypatch.setattr(pubmed, "MAX_CALLS_PER_SESSION", 2)
    search_literature("Spp1", species="mouse", use_cache=False)
    with pytest.raises(LiteratureUnavailable):
        search_literature("Acta1", species="mouse", use_cache=False)


# --- species labelling: the line that must never be crossed ------------------

def test_mouse_results_are_never_labelled_human(ncbi):
    mouse = search_literature("Spp1", species="mouse")
    for paper in mouse["papers"]:
        assert paper["queried_species"] == "mouse"
        assert paper["queried_symbol"] == "Spp1"
        assert paper["queried_species"] != "human"


def test_same_paper_from_both_queries_is_not_two_species_of_evidence(ncbi, monkeypatch):
    """PubMed symbol search is case-insensitive: 'Lbh' and 'LBH' are ONE query.

    So the mouse and human searches return the same record. Presented as two rows —
    one tagged mouse, one tagged human — that reads as a mouse finding corroborated
    by independent human work. It is one paper. The tool must say so.
    """
    monkeypatch.setattr(
        "src.literature.genes.resolve_symbols",
        lambda gene: {
            "input": gene, "input_type": "ensembl", "mouse_symbol": "Lbh",
            "human_symbols": ["LBH"], "ortholog_cardinality": "one_to_one",
            "targets": [{"symbol": "Lbh", "species": "mouse"},
                        {"symbol": "LBH", "species": "human"}],
            "note": "one_to_one",
        },
    )

    result = search_literature_tool("ENSMUSG00000024063")

    # The fake NCBI returns the same two PMIDs for both queries — as the real one does.
    assert result["total_retrieved"] == 4      # result ROWS
    assert result["unique_papers"] == 2        # actual PAPERS

    for search in result["searches"]:
        for paper in search["papers"]:
            assert paper["species_evidence"] == "ambiguous"
            assert sorted(paper["retrieved_by_queries"]) == ["human", "mouse"]
            assert "not independent" in paper["species_note"]
            assert "ONE paper" in paper["species_note"]

    assert "case-insensitive" in result["note"]


def test_distinct_papers_keep_their_species_label(ncbi, monkeypatch):
    """Overlap detection must not smear the label onto genuinely distinct results."""
    def fake_search(symbol, context_terms=None, species="unspecified", **kw):
        pmid = "11111111" if species == "mouse" else "22222222"
        return {
            "symbol": symbol, "species": species, "query": "q", "n_retrieved": 1,
            "papers": [{"pmid": pmid, "year": 2020, "title": "t", "abstract": "a",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "queried_symbol": symbol, "queried_species": species}],
        }

    monkeypatch.setattr("src.literature.pubmed.search_literature", fake_search)
    monkeypatch.setattr(
        "src.literature.genes.resolve_symbols",
        lambda gene: {
            "input": gene, "mouse_symbol": "Acta1", "human_symbols": ["ACTA1"],
            "ortholog_cardinality": "one_to_one", "input_type": "ensembl",
            "targets": [{"symbol": "Acta1", "species": "mouse"},
                        {"symbol": "ACTA1", "species": "human"}],
            "note": "n",
        },
    )

    result = search_literature_tool("ENSMUSG00000031972")

    assert result["unique_papers"] == 2
    labels = {
        p["pmid"]: p["species_evidence"]
        for s in result["searches"] for p in s["papers"]
    }
    assert labels == {"11111111": "mouse", "22222222": "human"}


def test_bare_symbol_species_is_unspecified_not_guessed():
    """Capitalisation is a convention, not evidence of species."""
    from src.literature.genes import resolve_symbols

    resolved = resolve_symbols("SPP1")
    assert resolved["targets"] == [{"symbol": "SPP1", "species": "unspecified"}]
    assert resolved["mouse_symbol"] is None


# --- grounding: PMIDs must trace to tool output ------------------------------

LIT_RESULT = {
    "gene": "Spp1",
    "total_retrieved": 1,
    "searches": [{
        "symbol": "Spp1",
        "species": "mouse",
        "n_retrieved": 1,
        "papers": [{
            "pmid": "38412345",
            "year": 2023,
            "title": "Spp1 expression in hindlimb unloaded mice",
            "abstract": "We unloaded 24 mice (p < 0.001). Spp1 was elevated 3.7-fold.",
            "url": "https://pubmed.ncbi.nlm.nih.gov/38412345/",
        }],
    }],
}


def test_retrieved_pmid_is_grounded():
    calls = [Call("search_literature", {"gene": "Spp1"}, LIT_RESULT)]

    check = verify(
        "The retrieved abstract for PMID 38412345 reports elevated Spp1.", calls
    )

    assert check.ok
    assert check.fabricated_pmids == []


def test_fabricated_pmid_is_withheld():
    calls = [Call("search_literature", {"gene": "Spp1"}, LIT_RESULT)]

    check = verify("See PMID 12345678, which proves the mechanism.", calls)

    assert not check.ok
    assert "12345678" in check.fabricated_pmids
    assert any("12345678" in item for item in check.unverified)


def test_fabricated_pubmed_url_is_withheld():
    calls = [Call("search_literature", {"gene": "Spp1"}, LIT_RESULT)]
    check = verify("See https://pubmed.ncbi.nlm.nih.gov/99999999/", calls)
    assert not check.ok
    assert "99999999" in check.fabricated_pmids


def test_pmid_digits_are_not_judged_as_a_quantity():
    """A real citation must not trip the NUMBER sweep on its own digits."""
    calls = [Call("search_literature", {"gene": "Spp1"}, LIT_RESULT)]
    check = verify("PMID 38412345 (2023) was retrieved.", calls)
    assert check.ok, check.unverified


def test_cited_pmids_reads_both_forms():
    assert cited_pmids("PMID: 111 and https://pubmed.ncbi.nlm.nih.gov/222/") == \
        ["111", "222"]


# --- the guard is not WEAKENED by literature ---------------------------------

def test_abstract_numbers_do_not_become_grounded_figures():
    """The whole reason literature results are excluded from the numeric pool.

    The abstract contains "24 mice", "p < 0.001" and "3.7-fold". If those leaked
    into the grounding pool, the agent could state 3.7 as though THIS app had
    computed it — retrieval would have punched a hole through the numerical guard.
    """
    calls = [Call("search_literature", {"gene": "Spp1"}, LIT_RESULT)]

    available = numbers_available(calls)

    assert 3.7 not in available
    assert 0.001 not in available
    assert 24.0 not in available
    # Only the whitelist survives: the PMID and the year.
    assert 38412345.0 in available
    assert 2023.0 in available

    # And end to end: quoting the abstract's fold change is withheld.
    check = verify("Spp1 rose 3.7-fold in our data.", calls)
    assert not check.ok
    assert "3.7" in check.unverified


def test_literature_tool_is_registered_as_a_literature_tool():
    assert "search_literature" in LITERATURE_TOOLS


def test_pmids_available_ignores_non_literature_tools():
    """A pmid-shaped field on a computational tool must not authorise a citation."""
    calls = [Call("get_de_results", {}, {"pmid": "38412345"})]
    assert pmids_available(calls) == set()


# --- the tool result the agent actually sees ---------------------------------

def test_tool_labels_every_paper_by_the_species_that_found_it(ncbi):
    result = search_literature_tool("Spp1")      # bare symbol -> one query

    assert result["total_retrieved"] == 2
    assert "RETRIEVAL ONLY" in result["note"]
    for search in result["searches"]:
        for paper in search["papers"]:
            assert paper["queried_species"] == "unspecified"


def test_tool_result_is_json_serialisable(ncbi):
    json.dumps(search_literature_tool("Spp1"), default=str)
