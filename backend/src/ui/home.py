"""The landing page.

Presentation only.

A CLAIM DELIBERATELY NOT MADE HERE: nothing about PubMed, PMIDs or literature.
There is no literature layer in this project — the agent has four tools and all
four are computation, and the guard traces figures to tool output only. Claiming
otherwise on the page whose subject is not over-claiming would be self-refuting.
"""

from __future__ import annotations

import streamlit as st

from src.ui.icons import helix, node, orbit, shield


def render(goto) -> None:
    st.markdown(
        f"""
<div class="landing">
  <div class="kicker">Space health · omics · agentic analysis</div>
  <h1>From space-biology data to defensible insight</h1>
  <div class="tagline">
    AI-guided differential expression and longitudinal analysis with scientific
    guardrails.
  </div>
  <div style="position:absolute;top:34px;right:20px;opacity:.32">{orbit(96)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="landing">
  <div class="intro">
    Space-biology datasets are often small, heterogeneous and distributed across
    multiple archives. Their structure determines which analyses are scientifically
    defensible, yet it is easy to apply inappropriate methods or overinterpret
    limited observations.
  </div>
  <div class="intro">
    AstroOmix is a research web application for analysing space-biology omics and
    longitudinal biosignal data. Researchers can upload their own data or begin with
    validated example studies. It validates the input, runs appropriate deterministic
    workflows, and provides a grounded AI research assistant that explains methods,
    interprets computed results and
    <em>highlights conclusions the evidence does not support.</em>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown('<div class="mc-rule"><strong>Workflows</strong></div>',
                unsafe_allow_html=True)

    left, right = st.columns(2)

    with left:
        st.markdown(
            f"""
<div class="wf">
  {node(26)}
  <h3>Differential Expression</h3>
  <p>Compare a flown group against a matched ground control, and find which genes
     actually responded to flight rather than to noise.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if st.button("Open Differential Expression", width="stretch",
                     type="primary", key="home_de"):
            goto("Differential Expression")

    with right:
        st.markdown(
            f"""
<div class="wf">
  {helix(26)}
  <h3>Longitudinal Analysis</h3>
  <p>Follow the same subjects across a mission — before launch, after return, through
     recovery — and model how a marker moves over time.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if st.button("Open Longitudinal Analysis", width="stretch",
                     type="primary", key="home_fc"):
            goto("Longitudinal Analysis")

    st.write("")
    st.markdown('<div class="mc-rule"><strong>Safeguards</strong></div>',
                unsafe_allow_html=True)

    # Three guarantees, each enforced by code you can go and read.
    st.markdown(
        f"""
<div class="honesty">
  <div class="card">
    {node(26)}
    <h4>Computed, not invented</h4>
    <p>
      The assistant has no independent knowledge of these datasets. It calls the
      same analysis code the workflows run and reports what comes back — every tool
      call it made is shown to you.
    </p>
  </div>
  <div class="card">
    {shield(26)}
    <h4>Verified before display</h4>
    <p>
      Every figure in an answer is checked against the actual analysis output before
      it reaches you. Anything that cannot be matched is withheld rather than shown.
    </p>
  </div>
  <div class="card">
    {helix(26)}
    <h4>Able to abstain</h4>
    <p>
      No clinical advice, ever. Thin data is flagged rather than modelled: below six
      timepoints it says so plainly, and it will tell you when a model reconstructs
      the observed points well but cannot forecast.
    </p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.caption("Method notes, engine choices and limitations are in **Methods**.")
