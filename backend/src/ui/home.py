"""The landing page — the front door.

Presentation only.

A CLAIM DELIBERATELY NOT MADE HERE: the honesty strip does not mention PubMed,
PMIDs or literature. There is no literature layer in this project — the agent has
four tools and all four are computation, and the grounding guard traces figures to
tool output only. Claiming otherwise on the page whose whole subject is not
over-claiming would be self-refuting.

The orientation section is a magazine intro, not a data grid: it describes what
these space-biology datasets ARE at a general level. It deliberately does not dump
datasets.yaml or quote a computed number — those live in the tabs, where they are
produced by the code rather than typed by hand.
"""

from __future__ import annotations

import streamlit as st

from src.ui.icons import helix, node, orbit, shield


def render(goto) -> None:
    st.markdown(
        f"""
<div class="landing">
  <div class="kicker">Space health · omics · agentic analysis</div>
  <h1>AstroOmix</h1>
  <div class="tagline">
    Agentic A/B testing and mission-phase forecasting for space health.
  </div>
  <div style="position:absolute;top:40px;right:20px;opacity:.35">{orbit(96)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="landing">
  <div class="intro">
    Space agencies are planning multi-year missions on a biology we have barely
    characterised. The data that exists is small-n, scattered across archives, and
    dangerously easy to over-read — seven timepoints will happily fit a
    confident-looking curve, and a model can win on score while being incapable of
    predicting anything at all.
  </div>
  <div class="intro">
    AstroOmix is a research tool for that problem. Bring your own space-biology
    data, or start from the built-in examples: it runs the rigorous analysis —
    differential expression, mission-phase forecasting — and puts an AI assistant
    on top that reads the result, explains the method, and
    <em>refuses to claim more than the data supports.</em>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown(
        '<div class="mc-rule"><strong>What this data is</strong></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class="landing">
  <div class="orient">
    Spaceflight biology has two characteristic shapes, and AstroOmix has a module
    for each.
    <br><br>
    <strong>Comparison.</strong> Fly one group, keep a matched group on the ground,
    and ask what changed. Rodent spaceflight studies do exactly this — muscle
    tissue from flown animals against ground controls — and the question is which
    genes actually responded to flight rather than to noise. With a handful of
    animals per group, most of the work is in <em>not</em> fooling yourself.
    <br><br>
    <strong>Trajectory.</strong> Follow the same crew across a mission — before
    launch, after return, through months of recovery — and ask how a physiological
    marker moves. Human spaceflight datasets are precious and tiny: a few
    individuals, a handful of draws. Modelling them is legitimate; presenting the
    result as a prediction usually is not.
    <br><br>
    The datasets shipped here are examples that demonstrate the tool, not the
    product. The product is what happens when you point it at your own.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown('<div class="mc-rule"><strong>How it stays honest</strong></div>',
                unsafe_allow_html=True)

    # Three guarantees, each enforced by code you can go and read. None
    # aspirational; none claiming a capability that does not exist.
    st.markdown(
        f"""
<div class="honesty">
  <div class="card">
    {node(28)}
    <h4>Every number traces to real computation</h4>
    <p>
      The assistant has no independent knowledge of these datasets. It calls the
      same analysis code the tabs run and reports what comes back — it cannot
      answer from memory, and every tool call it made is shown to you.
    </p>
  </div>
  <div class="card">
    {shield(28)}
    <h4>Verified at runtime, before you see it</h4>
    <p>
      Every figure in an answer is checked against the actual tool output before it
      is displayed. Anything that cannot be traced is sent back for correction —
      and if it still cannot be traced, it is <em>withheld</em>, not shown.
    </p>
  </div>
  <div class="card">
    {helix(28)}
    <h4>It refuses what the data cannot support</h4>
    <p>
      No clinical advice, ever. Thin data is flagged rather than forecast: below
      six timepoints it says so loudly, and at three it tells you plainly that no
      model could be validated.
    </p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown('<div class="mc-rule"><strong>Start here</strong></div>',
                unsafe_allow_html=True)

    left, middle, right = st.columns(3)
    with left:
        if st.button("🧬  Differential Expression", width="stretch",
                     type="primary", key="home_de"):
            goto("Differential Expression")
        st.caption("Flight vs. ground. Upload your counts, or open an example.")
    with middle:
        if st.button("📈  Forecasting", width="stretch", type="primary",
                     key="home_fc"):
            goto("Forecasting")
        st.caption("Mission-phase trajectories. Upload a series, or open an example.")
    with right:
        if st.button("📐  Methods", width="stretch", type="primary",
                     key="home_me"):
            goto("Methods")
        st.caption("Every engine choice, and the reasons — including the awkward ones.")
