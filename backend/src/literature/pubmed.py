"""Literature RETRIEVAL from PubMed. Not validation.

What this module does: given a gene symbol, it asks NCBI E-utilities for real
published papers, and returns exactly what NCBI sent back — PMID, title, journal,
year, publication type, abstract text, and the canonical PubMed URL. Every field
is transcribed, never inferred. A field NCBI did not supply comes back as None,
not as a guess.

What this module does NOT do, and must never be extended to do:

* It does not decide whether a paper *supports* anything. It has no opinion on
  what an abstract means. Retrieval is not evidence, and a hit is not a finding —
  a query for a gene AND "microgravity" returns papers where both strings occur,
  which is a search result, not a biological claim.
* It does not merge species. A query built from the mouse symbol returns papers
  found *by the mouse symbol*, and every record says so. Mouse evidence relabelled
  as human evidence is the single most dangerous thing a cross-species tool can
  do, so species is a property of the QUERY, recorded at the point the query is
  built, and it travels with the record.
* It does not pad. Zero results is a real, honest, expected answer. Loosening the
  query until something comes back would manufacture the appearance of evidence.

Numbers in these results are NOT grounding material
---------------------------------------------------
Abstracts are dense with figures — p-values, cohort sizes, fold changes. Those
numbers describe someone else's experiment, not ours. `src/agent/grounding.py`
therefore excludes literature results from the numeric grounding pool entirely,
whitelisting only PMIDs and years. If that exclusion were dropped, an abstract's
"p < 0.001" would become a number the agent could state as though this app had
computed it. See LITERATURE_TOOLS there.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import requests

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# NCBI asks every client to identify itself. They are within their rights to
# block traffic that does not.
TOOL_NAME = "AstroOmix"
CONTACT_EMAIL = "your.email@example.com"   # placeholder — swap for a real address

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "literature"

# NCBI's unauthenticated ceiling is 3 requests/second. We stay under it rather
# than at it: being throttled mid-demo is a self-inflicted wound.
MIN_INTERVAL_SECONDS = 0.4
TIMEOUT_SECONDS = 12
MAX_RETRIES = 3

# A session cannot spend the whole demo hammering NCBI. This is a circuit breaker,
# not a quota: it exists so a runaway agent loop cannot get us rate-limited.
MAX_CALLS_PER_SESSION = 40

DEFAULT_CONTEXT = (
    "spaceflight OR microgravity OR \"hindlimb unloading\" OR \"muscle atrophy\""
)

_last_request_at = 0.0
_calls_this_session = 0


class LiteratureUnavailable(RuntimeError):
    """NCBI could not be reached. A degraded state, not a crash."""


def _throttle() -> None:
    global _last_request_at
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _get(endpoint: str, params: dict) -> requests.Response:
    """One E-utilities call, throttled, with backoff on the errors worth retrying."""
    global _calls_this_session

    if _calls_this_session >= MAX_CALLS_PER_SESSION:
        raise LiteratureUnavailable(
            f"Literature retrieval limit for this session ({MAX_CALLS_PER_SESSION} "
            "requests) reached."
        )

    params = {**params, "tool": TOOL_NAME, "email": CONTACT_EMAIL}
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        _throttle()
        _calls_this_session += 1
        try:
            response = requests.get(
                f"{BASE}/{endpoint}", params=params, timeout=TIMEOUT_SECONDS
            )
            # 429 = throttled, 5xx = their side. Both are worth waiting out.
            # A 4xx that is not 429 is our bug and will not fix itself.
            if response.status_code == 429 or response.status_code >= 500:
                last_error = LiteratureUnavailable(
                    f"NCBI returned HTTP {response.status_code}."
                )
                time.sleep(0.6 * (2 ** attempt))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            time.sleep(0.6 * (2 ** attempt))

    raise LiteratureUnavailable(f"NCBI E-utilities unreachable: {last_error}")


def _cache_path(key: dict) -> Path:
    digest = hashlib.sha256(
        json.dumps(key, sort_keys=True).encode()
    ).hexdigest()[:12]
    return CACHE_DIR / f"{key['symbol']}__{key['species']}__{digest}.json"


def build_query(symbol: str, context_terms: str | None = None) -> str:
    """The gene AND the space-biology context. Both halves are required.

    Without the context clause a symbol like `Cd36` returns thousands of papers
    about lipid metabolism, and the top 5 would be whatever PubMed ranked first —
    presented next to a spaceflight result, that reads as spaceflight literature
    when it is nothing of the kind.
    """
    context = (context_terms or DEFAULT_CONTEXT).strip()
    return f"({symbol}) AND ({context})"


def _text(node, path: str) -> str | None:
    found = node.find(path)
    if found is None:
        return None
    # itertext(): abstracts carry inline <i>/<sup> markup, and .text alone would
    # truncate at the first tag — silently returning half an abstract.
    value = "".join(found.itertext()).strip()
    return value or None


def _parse_article(article) -> dict | None:
    """Transcribe ONE PubmedArticle. Every field comes from the XML or is None."""
    pmid = _text(article, ".//MedlineCitation/PMID")
    if not pmid or not pmid.isdigit():
        return None      # without a real PMID there is no verifiable record

    # An abstract can be split into labelled sections (BACKGROUND/METHODS/...).
    # Joining them preserves the whole text; taking the first would drop the results.
    sections = []
    for block in article.findall(".//Abstract/AbstractText"):
        body = "".join(block.itertext()).strip()
        if not body:
            continue
        label = block.get("Label")
        sections.append(f"{label}: {body}" if label else body)
    abstract = "\n\n".join(sections) or None

    year = _text(article, ".//JournalIssue/PubDate/Year")
    if year is None:
        # Some records carry only a MedlineDate ("2019 Jan-Feb"). Take the year
        # from it if one is literally present; never infer one.
        medline = _text(article, ".//JournalIssue/PubDate/MedlineDate") or ""
        match = re.search(r"\b(19|20)\d{2}\b", medline)
        year = match.group() if match else None

    types = [
        "".join(t.itertext()).strip()
        for t in article.findall(".//PublicationTypeList/PublicationType")
    ]
    types = [t for t in types if t]

    return {
        "pmid": pmid,
        "title": _text(article, ".//ArticleTitle"),
        "journal": _text(article, ".//Journal/Title"),
        "year": int(year) if year and year.isdigit() else None,
        "publication_types": types,
        # Reviews and primary research are different kinds of evidence and a
        # reader must be able to tell them apart at a glance.
        "is_review": any("review" in t.lower() for t in types),
        "abstract": abstract,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def search_literature(
    symbol: str,
    context_terms: str | None = None,
    species: str = "unspecified",
    retmax: int = 5,
    use_cache: bool = True,
) -> dict:
    """Retrieve real PubMed records for one symbol. Returns only what NCBI sent.

    `species` is the species of the SYMBOL being searched — it is carried onto
    every record so a mouse-symbol hit can never be read as human evidence.

    Raises LiteratureUnavailable if NCBI cannot be reached; the caller decides how
    to degrade.
    """
    symbol = (symbol or "").strip()
    if not symbol:
        return {"symbol": symbol, "species": species, "n_retrieved": 0, "papers": []}

    query = build_query(symbol, context_terms)
    key = {"symbol": symbol, "species": species, "query": query, "retmax": retmax}
    cache = _cache_path(key)

    if use_cache and cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))

    search = _get("esearch.fcgi", {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max(1, min(retmax, 10)),
        "sort": "relevance",
    }).json()

    pmids = search.get("esearchresult", {}).get("idlist", [])

    papers: list[dict] = []
    if pmids:
        xml = _get("efetch.fcgi", {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }).text
        root = ElementTree.fromstring(xml)
        for article in root.findall(".//PubmedArticle"):
            record = _parse_article(article)
            if record is None:
                continue
            # Species and symbol describe the QUERY that found this paper, and
            # they are stamped here so nothing downstream has to reconstruct them.
            record["queried_symbol"] = symbol
            record["queried_species"] = species
            papers.append(record)

    payload = {
        "symbol": symbol,
        "species": species,
        "query": query,
        "n_retrieved": len(papers),
        "papers": papers,
        "retrieval_note": (
            "These papers were RETRIEVED by a keyword query. Retrieval is not "
            "endorsement: a hit means the gene symbol and a spaceflight term "
            "co-occur in the record, not that the paper studied this gene in "
            "spaceflight, and not that it supports any claim about it."
        ),
    }

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def reset_session_budget() -> None:
    """Test seam / new session: clear the per-session request counter."""
    global _calls_this_session
    _calls_this_session = 0
