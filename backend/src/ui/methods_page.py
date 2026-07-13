"""The Methods page — capability cards.

States what the methods ARE. The engineering narrative — the dispersion bugs, the
explosive-AR fix, the memory figures, the ortholog cardinality investigation —
lives in docs/METHODS.md and is not retold here. A product's methods page is a
specification, not a development log; a reviewer wants to know what was done, not
how it was debugged.
"""

from __future__ import annotations

import streamlit as st


def _card(number: str, title: str, items: list[str]) -> str:
    bullets = "".join(f"<li>{item}</li>" for item in items)
    return f"""
<div class="mcard">
  <div class="num">{number}</div>
  <h4>{title}</h4>
  <ul>{bullets}</ul>
</div>"""


def render() -> None:
    st.header("Methods")

    st.markdown(
        """
<div class="principle">
  <strong>One principle governs everything below:</strong> a result is shown only
  if it can be computed, and it is qualified whenever the data cannot support the
  conclusion a reader would naturally draw from it.
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")

    left, right = st.columns(2)

    with left:
        st.markdown(
            _card("01", "Supported workflows", [
                "<strong>Bulk RNA-seq differential expression</strong> — a flown "
                "group against a matched ground control.",
                "<strong>Longitudinal biosignal modelling</strong> — repeated "
                "measures on the same subjects across a mission timeline.",
            ]) +
            _card("02", "Data validation", [
                "<strong>Expected counts</strong> — fractional RSEM counts are "
                "rounded to integers, which the negative-binomial model requires. "
                "Non-numeric, negative and non-finite values are rejected, not coerced.",
                "<strong>Sample assignment</strong> — every sample must resolve to "
                "flight or ground; an unassignable sample is an error, never a "
                "silent drop.",
                "<strong>Time-axis conversion</strong> — timepoints are converted to "
                "mission days before any model sees them. Raw labels are rejected: "
                "they would collapse the flight out of the timeline.",
                "<strong>Minimum timepoints</strong> — fewer than three cannot be "
                "fitted and are refused.",
            ]) +
            _card("03", "Statistical methods", [
                "<strong>PyDESeq2</strong> — worked RNA-seq examples. Median-of-ratios "
                "normalisation, empirical-Bayes dispersion shrinkage, Wald test.",
                "<strong>Resource-safe NB-GLM</strong> — public uploads. A "
                "single-process negative-binomial GLM sized for hosted compute.",
                "<strong>Prophet, ARIMA and LightGBM</strong> — illustrative "
                "comparison on longitudinal data, not a model recommendation.",
            ]),
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            _card("04", "Evaluation", [
                "<strong>FDR correction</strong> — Benjamini–Hochberg across all "
                "tested genes. Genes dropped by independent filtering are reported "
                "as having no result, never as non-significant.",
                "<strong>Leave-one-out reconstruction error</strong> — each timepoint "
                "is held out once and predicted from the rest.",
                "<strong>Interpolation is not extrapolation</strong> — the LOO score "
                "measures how well a model reconstructs the points it was given. It "
                "does not measure forecasting ability, and it never validates a "
                "projection beyond the last observation.",
            ]) +
            _card("05", "AI grounding", [
                "<strong>Tool-based retrieval</strong> — the assistant has no "
                "independent knowledge of the data. It calls the same analysis code "
                "the workflows run, and every call it makes is shown.",
                "<strong>Runtime numerical verification</strong> — every figure in an "
                "answer is checked against the actual analysis output before it is "
                "displayed.",
                "<strong>Withholding policy</strong> — a figure that cannot be matched "
                "is sent back once for repair, and withheld if it still cannot be "
                "matched. It is never shown unverified.",
            ]) +
            _card("06", "Limitations", [
                "<strong>Small sample sizes</strong> — spaceflight cohorts are tiny. "
                "Results are descriptive and hypothesis-generating.",
                "<strong>Hosted compute constraints</strong> — upload size and engine "
                "choice are bounded by the hosted demo, not by the biology.",
                "<strong>No clinical claims</strong> — nothing here is diagnostic, and "
                "no output is a basis for a health decision.",
                "<strong>No validated cross-species integration</strong> — mouse-human "
                "orthology is many-to-many and lossy; any cross-species link is "
                "evidence for a human to weigh, not a statistical result.",
            ]),
            unsafe_allow_html=True,
        )

    st.write("")
    st.caption(
        "[Detailed technical documentation](docs/METHODS.md) · "
        "[Data provenance](docs/DATA_NOTES.md) · "
        "[View source code](https://github.com/Mithrasen/AstroOmix)"
    )
