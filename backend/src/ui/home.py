"""The Case — the landing page and entry point.

Presentation only. Every claim on this page had to be checkable against something
that actually exists in the repo, which is why the "how it stays honest" strip
says what it says and no more.

NOTE ON A CLAIM NOT MADE HERE: the brief asked for "every number traces to real
computation or a real PubMed PMID." There is no literature layer in this project —
no PubMed tool, no PMID, anywhere. The agent has four tools and all four are
computation (list_analytes, get_forecast, list_studies, get_de_results); the
grounding guard traces figures to tool output only. Putting a PMID claim on the
landing page would be a fabricated capability claim on the very page whose subject
is not over-claiming. So the strip states the three guarantees the code actually
makes, each of which is enforced somewhere you can go and read.
"""

from __future__ import annotations

import streamlit as st

from src.ui.icons import helix, node, orbit, shield

HERO_QUESTION = "Should I trust LightGBM's day-300 prediction for neutrophils?"


def render(goto) -> None:
    """`goto(page_name)` switches the sidebar page. Nav plumbing, nothing more."""

    # --- 1. the stakes, then the differentiator ------------------------------
    st.markdown(
        f"""
<div class="hero">
  <div style="position:absolute;top:22px;right:26px;opacity:.5">{orbit(72)}</div>
  <div class="stakes">
    Space agencies are planning multi-year missions on a biology we have barely
    characterised. The data that does exist is small-n, scattered across archives,
    and dangerously easy to over-read — a handful of timepoints will happily fit a
    confident-looking curve.
  </div>
  <h1>
    AstroOmix analyses space-biology omics data, interprets it,
    <span class="lede">grounds every claim in real computation</span> —
    and <span class="refuse">refuses to pretend it knows more than the data
    supports.</span>
  </h1>
  <div class="sub">
    Bring your own space-biology data, or start from the built-in examples. The
    assistant runs the analysis, reads the result, and tells you where it is thin.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")

    # --- 2. who it is for ----------------------------------------------------
    st.markdown(
        """
<div class="persona">
  <div class="who">Built for</div>
  <p>
    <strong>The space-biology researcher.</strong> A bioinformatician or
    physiologist working with omics from spaceflight archives — NASA OSDR/GeneLab
    and beyond — comparing flight against ground control, and modelling how a
    body changes across a mission. The datasets shipped here are
    <em>examples</em>; the product is the analysis and the interpretation you
    point at your own data.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")

    # --- 3. calls to action --------------------------------------------------
    primary, second, third = st.columns([1.35, 1, 1])

    with primary:
        if st.button("🛰️  Ask the Research Assistant", type="primary",
                     width="stretch", key="cta_assistant"):
            # Pre-load the verified hero question. Presentation plumbing only —
            # it lands in the input; the agent path is untouched.
            st.session_state["prefill_question"] = HERO_QUESTION
            goto("Research Assistant")

        st.caption(f"Pre-loads: *“{HERO_QUESTION}”*")

    with second:
        if st.button("🧬  Explore the analysis modules", width="stretch",
                     key="cta_modules"):
            goto("Differential Expression")
        st.caption("Differential expression, forecasting, integration.")

    with third:
        if st.button("📤  Upload your own data", width="stretch", key="cta_upload"):
            goto("Differential Expression")
        st.caption("Your counts or your time series — same pipeline, same caveats.")

    st.write("")
    st.markdown('<div class="mc-rule"><strong>How it stays honest</strong></div>',
                unsafe_allow_html=True)

    # --- 4. the differentiator, stated plainly ------------------------------
    #
    # Each of these three is enforced by code you can go and read. None of them is
    # aspirational, and none claims a capability that does not exist.
    st.markdown(
        f"""
<div class="honesty">
  <div class="card">
    {node(30)}
    <h4>Every number traces to real computation</h4>
    <p>
      The assistant has no independent knowledge of these datasets. It calls the
      same analysis code the pages run — DESeq2, Prophet/ARIMA/LightGBM, the MGI
      ortholog graph — and reports what comes back. It cannot answer from memory,
      and every tool call it made is shown to you.
    </p>
  </div>
  <div class="card">
    {shield(30)}
    <h4>Verified at runtime, before you see it</h4>
    <p>
      Every figure in an answer is checked against the actual tool output before
      it is displayed. Anything that cannot be traced is sent back for correction,
      and if it still cannot be traced it is <em>withheld</em> — not shown. This
      runs on every response, not just in the test suite.
    </p>
  </div>
  <div class="card">
    {helix(30)}
    <h4>It refuses what the data cannot support</h4>
    <p>
      No clinical advice, ever. Thin data is flagged, not forecast: below six
      timepoints it says so loudly, and at three it tells you plainly that
      <em>no model could be validated</em>. A model that wins on score but cannot
      extrapolate is called out rather than recommended.
    </p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.caption(
        "The built-in examples are NASA OSDR rodent spaceflight RNA-seq (OSD-104 "
        "soleus, OSD-105 tibialis anterior — 6 flight vs 6 ground) and the SpaceX "
        "Inspiration4 crew blood panel (4 crew, 7 timepoints). They are there to "
        "demonstrate the tool, not to define it."
    )
