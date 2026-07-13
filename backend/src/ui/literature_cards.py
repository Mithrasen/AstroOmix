"""Retrieved papers, shown so the READER can judge them.

The point of showing the abstract is that it takes the judgement away from the
model. The agent is constrained by its system prompt to characterise a paper only
in the words of the retrieved abstract — but a constraint is a promise, and a
promise is not a proof. Putting the actual abstract on the page next to the paper
means the reader can check the characterisation against the source in one glance,
without leaving the app and without trusting us.

So: real title, real PMID, real journal, real year, real type, real species label,
real abstract, real PubMed link. If a field came back empty from NCBI it is shown
as unavailable. Nothing here is summarised, inferred, or filled in.

The two signals are never merged
--------------------------------
"Computation: verified" and "Literature: retrieved" are different claims and are
drawn as different badges. Verified means every number traced to a tool result.
Retrieved means a keyword query returned some papers — it is not a quality mark,
it is not peer endorsement, and it says nothing about whether those papers support
anything. A single green "verified" badge covering both would launder a search
result into a validation, which is the exact failure this feature is built to
avoid.
"""

from __future__ import annotations

import streamlit as st

SPECIES_LABEL = {
    "mouse": ("Mouse-symbol query", "#d8b968"),
    "human": ("Human-symbol query", "#5aa9e6"),
    # Not "Mouse + Human" — that phrasing is the very claim this label exists to
    # deny. The same record came back from both queries because PubMed's symbol
    # search is case-insensitive; it is one paper, not two species of evidence.
    "ambiguous": ("Species ambiguous — one paper, both queries", "#d8b968"),
    "unspecified": ("Species not resolved", "#8b96a8"),
}


def literature_searches(tool_calls) -> list[dict]:
    """Every search_literature result in this answer's tool calls."""
    searches = []
    for call in tool_calls:
        name = call["name"] if isinstance(call, dict) else call.name
        if name != "search_literature":
            continue
        result = call["result"] if isinstance(call, dict) else call.result
        if isinstance(result, dict):
            searches.append(result)
    return searches


def render_signals(tool_calls, withheld) -> None:
    """Two badges, two meanings. Never one."""
    searches = literature_searches(tool_calls)

    computation = (
        '<span class="sig sig-bad">Computation: withheld</span>' if withheld
        else '<span class="sig sig-ok">Computation: verified</span>'
    )

    literature = ""
    if searches:
        unavailable = any(s.get("literature_unavailable") for s in searches)
        total = sum(s.get("total_retrieved", 0) for s in searches)
        if unavailable:
            literature = '<span class="sig sig-off">Literature: unavailable</span>'
        elif total:
            literature = (
                f'<span class="sig sig-lit">Literature: retrieved '
                f'({total} paper{"s" if total != 1 else ""})</span>'
            )
        else:
            literature = '<span class="sig sig-off">Literature: none retrieved</span>'

    st.markdown(
        f'<div class="sigrow">{computation}{literature}</div>',
        unsafe_allow_html=True,
    )


def render_papers(tool_calls) -> None:
    """The retrieved papers themselves — abstract included, judgement left to the reader."""
    searches = literature_searches(tool_calls)
    if not searches:
        return

    if any(s.get("literature_unavailable") for s in searches):
        st.info(
            "Literature retrieval is temporarily unavailable (PubMed could not be "
            "reached). The analysis above is unaffected.",
            icon="📚",
        )
        return

    # ONE row per unique PMID. PubMed's symbol search is case-insensitive, so the
    # mouse and human queries return the same record; drawing it twice would show a
    # single paper as if it were mouse evidence AND separate human evidence. It is
    # drawn once, and the ambiguity is printed on it.
    papers: list[tuple[dict, dict]] = []
    drawn: set[str] = set()
    for result in searches:
        for search in result.get("searches", []):
            for paper in search.get("papers", []):
                if paper.get("pmid") in drawn:
                    continue
                drawn.add(paper.get("pmid"))
                papers.append((search, paper))

    if not papers:
        # An honest zero. Said in full, because half of it — "none retrieved" —
        # is the half a reader is most likely to over-read.
        st.info(
            "**No relevant literature was retrieved** for this query. That means this "
            "search returned nothing — it is not evidence that no such literature "
            "exists.",
            icon="📚",
        )
        return

    st.markdown(
        '<div class="mc-rule"><strong>Literature retrieval</strong></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Papers RETRIEVED by keyword search, for you to judge. Retrieval is not "
        "validation: a hit means the gene symbol and a spaceflight term co-occur in "
        "the record. Read the abstract before drawing any conclusion."
    )

    for search, paper in papers:
        evidence = paper.get("species_evidence") or search.get("species", "unspecified")
        label, colour = SPECIES_LABEL.get(evidence, SPECIES_LABEL["unspecified"])

        kind = "Review" if paper.get("is_review") else "Primary research"
        if not paper.get("publication_types"):
            kind = "Type not stated"

        queried = paper.get("retrieved_by_queries") or [search.get("species")]
        symbols = paper.get("queried_symbol") or search.get("symbol")
        query_tag = (
            f"retrieved by the {' and '.join(queried)} symbol quer"
            f"{'ies' if len(queried) > 1 else 'y'}"
        )

        title = paper.get("title") or "(no title returned)"
        journal = paper.get("journal") or "journal not stated"
        year = paper.get("year") or "year not stated"
        pmid = paper.get("pmid")

        st.markdown(
            f"""
<div class="paper">
  <div class="paper-tags">
    <span class="tag" style="color:{colour};border-color:{colour}66">{label}</span>
    <span class="tag">{kind}</span>
    <span class="tag">{query_tag}</span>
  </div>
  <a class="paper-title" href="{paper.get('url')}" target="_blank">{title}</a>
  <div class="paper-meta">{journal} · {year} · PMID
    <a href="{paper.get('url')}" target="_blank">{pmid}</a></div>
</div>
""",
            unsafe_allow_html=True,
        )

        if paper.get("species_evidence") == "ambiguous":
            st.caption(f"⚠️ {paper.get('species_note')}")

        abstract = paper.get("abstract")
        with st.expander("Retrieved abstract"):
            if abstract:
                st.markdown(abstract)
                st.caption(
                    "Verbatim from PubMed. Any characterisation of this paper must "
                    "be supported by this text — including which organism it studied."
                )
            else:
                st.caption("PubMed returned no abstract for this record.")
