"""AstroOmix — Streamlit front end.

A UI swap, not a rewrite. Every number on every page comes from the same
functions the FastAPI service used:

    run_deseq2 / _cached_results   backend/routers/abtest.py, src/abtest/deseq.py
    _round / _to_records           backend/routers/abtest.py   (display rounding)
    _build                         backend/routers/forecast.py (model comparison)
    cross_reference                backend/src/integrate/cross_reference.py
    allow_refresh                  backend/src/settings.py     (the OOM guard)

No differential expression, forecasting, or orthology logic is reimplemented
here. If a number differs from what the API served, that is a bug in this file.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
DOCS = ROOT / "docs"

# The analysis package lives under backend/ and imports itself as `src.*` /
# `routers.*`, so backend/ must be on the path before anything else is imported.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routers.abtest import (  # noqa: E402
    _abtest_accessions,
    _cached_results,
    _to_records,
)
from routers.forecast import (  # noqa: E402
    _build,
    _cache_path,
    _valid_analytes,
    _valid_crew,
)
from routers.integrate import _sanitise  # noqa: E402
from routers.studies import load_studies  # noqa: E402
from src.integrate.cross_reference import cross_reference  # noqa: E402
from src.settings import allow_refresh  # noqa: E402
from src.ui.components import (  # noqa: E402
    animated_counters,
    cardinality_counters,
    mission_timeline,
)
from src.ui.theme import inject_theme  # noqa: E402

st.set_page_config(
    page_title="AstroOmix",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Styling only, and it must land before any page content is painted.
inject_theme()

MODEL_COLORS = {"prophet": "#5aa9e6", "arima": "#c9a227", "lightgbm": "#e05c5c"}

CARDINALITY = {
    "one_to_one": ("one-to-one", "#4ec9a0", "Unambiguous. One mouse gene, one human gene."),
    "one_to_many": ("one-to-many", "#d8b968", "One mouse gene splits across several human genes."),
    "many_to_one": ("many-to-one", "#d89a68", "Several mouse genes collapse onto the same human gene."),
    "many_to_many": ("many-to-many", "#d87c8a", "Ambiguous in both directions."),
    "no_ortholog": ("no ortholog", "#6b7688", "No human counterpart in MGI. Not mappable."),
}

TIER = {
    "one_to_one": "clean",
    "one_to_many": "ambiguous — read the mapping",
    "many_to_one": "ambiguous — read the mapping",
    "many_to_many": "ambiguous — read the mapping",
    "no_ortholog": "not mappable",
}


# --- data access (thin wrappers around the existing functions) ---------------

@st.cache_data(show_spinner=False)
def abtest_results(accession: str, refresh: bool = False) -> pd.DataFrame:
    """Reuses the committed cache in backend/data/cache/de/ — instant, not a live
    DESeq2 run."""
    return _cached_results(accession, refresh=refresh)


@st.cache_data(show_spinner=False)
def forecast_payload(analyte: str, crew: str, extra_days: int) -> dict:
    """Same on-disk cache the API route used, then the same `_build` if it misses."""
    path = _cache_path(analyte, crew, extra_days)
    if path.is_file():
        return json.loads(path.read_text())
    return _build(analyte, crew, extra_days)


@st.cache_data(show_spinner=False)
def integrate_payload(accession: str, limit: int = 500) -> dict:
    return _sanitise(cross_reference(accession, limit=limit))


@st.cache_data(show_spinner=False)
def studies() -> list[dict]:
    return load_studies()


# --- pages -------------------------------------------------------------------

def page_study_explorer():
    st.header("Study Explorer")
    st.caption(
        "Datasets pulled live from NASA OSDR. Several plausible-looking accessions do "
        "not contain what their titles suggest — see docs/DATA_NOTES.md."
    )

    # Hovering a node shows that dataset's real record from config/datasets.yaml —
    # organism, tissue, assay, design, notes. Nothing decorative is invented.
    mission_timeline(studies())
    st.caption(
        "Missions in flight order. Hover a node for the dataset's record. "
        "Rodent Research 1 flew before Inspiration4 (launched 2021-09-16, the anchor "
        "of the mission-day axis used throughout this app)."
    )

    frame = pd.DataFrame(studies())
    st.dataframe(
        frame[["accession", "label", "organism", "tissue", "assay", "module", "design", "notes"]],
        width="stretch",
        hide_index=True,
    )


def page_abtest():
    st.header("A/B Testing — spaceflight vs. ground control")

    catalogue = {s["accession"]: s for s in studies() if s["module"] == "abtest"}
    left, right = st.columns([2, 3])

    with left:
        accession = st.selectbox(
            "Dataset",
            sorted(_abtest_accessions()),
            format_func=lambda a: f"{a} — {catalogue[a]['tissue']}",
        )

    with right:
        force = st.checkbox(
            "Force refresh (re-run DESeq2)",
            value=False,
            help="Disabled unless ALLOW_REFRESH=true.",
        )

    # Same guard as the API, same reason: an uncached DESeq2 run peaks at ~2.4 GB
    # across ~18 workers. We reuse allow_refresh() rather than restating the rule.
    if force and not allow_refresh():
        st.error(
            "**Refresh is disabled in this environment.** Re-running DESeq2 uncached "
            "peaks at ~2.4 GB of memory, which exceeds this deployment's limit and "
            "would take the app down. Set `ALLOW_REFRESH=true` to enable it locally. "
            "Showing the cached result instead."
        )
        force = False

    study = catalogue[accession]
    st.caption(f"{study['design']} · {study['assay']} · {study['notes']}")

    results = abtest_results(accession, refresh=force)

    # Significance is counted on the UNROUNDED table. Counting it on the rounded
    # display values lets a gene at padj 0.0499 round to 0.05 and vanish.
    n_significant = int((results["padj"] < 0.05).sum())

    # The exact display rounding the API used, so the numbers match what was
    # already validated.
    records = _to_records(results)
    table = pd.DataFrame(records)

    # Same three values as the st.metric row it replaces — the count-up animation
    # lands exactly on the real number and never alters it.
    animated_counters([
        {"label": "Genes tested", "value": len(table)},
        {"label": "FDR < 0.05", "value": n_significant, "color": "#4ec9a0"},
        {"label": "Method", "text": "DESeq2 (pydeseq2)", "color": "#5aa9e6"},
    ])

    st.plotly_chart(volcano(table), width="stretch")

    st.subheader("Hits")
    only_significant = st.checkbox("Significant only (FDR < 0.05)", value=True)
    query = st.text_input("Filter by gene ID", "")

    view = table
    if only_significant:
        view = view[view["padj"].notna() & (view["padj"] < 0.05)]
    if query.strip():
        view = view[view["gene"].str.contains(query.strip(), case=False, na=False)]

    st.dataframe(
        view.sort_values("padj", na_position="last"),
        width="stretch",
        hide_index=True,
        column_config={
            "gene": "Gene",
            "base_mean": st.column_config.NumberColumn("Base mean", format="%.1f"),
            "log2fc": st.column_config.NumberColumn("log2FC", format="%.3f"),
            "pvalue": st.column_config.NumberColumn("p-value", format="%.2e"),
            "padj": st.column_config.NumberColumn("padj (FDR)", format="%.2e"),
        },
    )
    st.caption(
        f"{len(view):,} rows. Positive log2FC means higher expression in flight. "
        "Genes with a blank padj were dropped by DESeq2's independent filtering — "
        "that is 'no result', not 'not significant'."
    )


def volcano(table: pd.DataFrame) -> go.Figure:
    """All genes, no thinning — Scattergl renders 22k points without breaking a
    sweat (the old Recharts SVG chart had to subsample)."""
    plottable = table[table["padj"].notna() & (table["padj"] > 0)].copy()
    plottable["neglog10"] = -np.log10(plottable["padj"].to_numpy(dtype=float))

    def bucket(row):
        if row["padj"] >= 0.05:
            return "not significant"
        if row["log2fc"] >= 1:
            return "up in flight"
        if row["log2fc"] <= -1:
            return "down in flight"
        return "significant, |log2FC| < 1"

    plottable["bucket"] = plottable.apply(bucket, axis=1)
    colors = {
        "not significant": "#3d4655",
        "significant, |log2FC| < 1": "#c9a227",
        "up in flight": "#e05c5c",
        "down in flight": "#4d8fd6",
    }

    figure = go.Figure()
    for name in ["not significant", "significant, |log2FC| < 1", "down in flight", "up in flight"]:
        subset = plottable[plottable["bucket"] == name]
        figure.add_trace(go.Scattergl(
            x=subset["log2fc"], y=subset["neglog10"],
            mode="markers", name=name,
            marker=dict(size=4, color=colors[name], opacity=0.75),
            text=subset["gene"],
            hovertemplate="%{text}<br>log2FC %{x:.3f}<br>-log10(padj) %{y:.1f}<extra></extra>",
        ))

    figure.add_hline(y=-math.log10(0.05), line_dash="dash", line_color="#5a6478")
    for x in (-1, 1):
        figure.add_vline(x=x, line_dash="dash", line_color="#5a6478")

    figure.update_layout(
        template="plotly_dark",
        height=460,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="log2 fold change (flight / ground)",
        yaxis_title="-log10(padj)",
        legend=dict(orientation="h", y=1.1),
    )
    n_dropped = len(table) - len(plottable)
    figure.add_annotation(
        text=f"{n_dropped:,} genes have no adjusted p-value and cannot be plotted",
        xref="paper", yref="paper", x=0, y=-0.18, showarrow=False,
        font=dict(size=11, color="#8b96a8"),
    )
    return figure


def page_forecasting():
    st.header("Forecasting — Inspiration4 molecular trajectories")

    left, middle, right = st.columns(3)
    with left:
        analyte = st.selectbox(
            "Analyte", _valid_analytes(),
            index=_valid_analytes().index("absolute_neutrophils"),
            format_func=lambda a: a.replace("_", " "),
        )
    with middle:
        crew = st.selectbox(
            "Crew", _valid_crew(),
            format_func=lambda c: "mean of 4 crew" if c == "mean" else c,
        )
    with right:
        # Matches the API's le=365 bound.
        extra_days = st.number_input(
            "What-if: days past last draw", min_value=0, max_value=365, value=30, step=1,
        )

    with st.spinner("Fitting models…"):
        data = forecast_payload(analyte, crew, int(extra_days))

    st.caption(data["caveat"])
    st.plotly_chart(trajectory(data), width="stretch")

    st.subheader("Model comparison — leave-one-out CV")

    best = data["comparison"]["best_by_mae"]
    warning = data["comparison"].get("best_by_mae_warning")

    st.markdown(f"**Best by MAE:** :{'red' if warning else 'green'}[{best}]")

    # The trap: LightGBM usually wins LOO and cannot extrapolate at all. This has
    # to be impossible to miss, so it sits directly under the callout.
    if warning:
        st.warning(f"**“Best” does not mean “best forecaster.”**\n\n{warning}", icon="⚠️")

    metrics = pd.DataFrame(data["comparison"]["metrics"]).T.reset_index()
    metrics.columns = ["model", "MAE", "RMSE", "MAPE %", "folds", "failed"]
    metrics["uncertainty"] = metrics["model"].map(
        lambda m: "95% interval" if data["curves"][m]["has_uncertainty"]
        else "no uncertainty estimate"
    )
    st.dataframe(metrics, width="stretch", hide_index=True)
    st.caption(
        f"LOO-CV holds out each of the {data['n_timepoints']} timepoints once and fits "
        "on the rest. It measures how well a model **interpolates** the observed "
        "trajectory — it does **not** validate the what-if extrapolation below."
    )

    if data.get("whatif"):
        st.subheader(f"What-if: {int(extra_days)} days past the last draw")
        columns = st.columns(len(data["whatif"]))
        for column, (model, scenario) in zip(columns, data["whatif"].items()):
            with column:
                st.markdown(f"**:{'blue' if model == 'prophet' else 'orange'}[{model}]** "
                            f"· mission day {scenario['day']}")
                st.metric(data["unit"], f"{scenario['yhat']:.1f}")
                if scenario["yhat_lower"] is not None:
                    st.caption(
                        f"95% interval: {scenario['yhat_lower']:.1f} – "
                        f"{scenario['yhat_upper']:.1f}"
                    )
                else:
                    st.caption("no uncertainty estimate")
                if scenario.get("flat_extrapolation"):
                    st.error(f"**Not a projection.** {scenario['caveat']}", icon="⚠️")


def trajectory(data: dict) -> go.Figure:
    figure = go.Figure()

    observed_days = [p["day"] for p in data["observed"]]
    observed_values = [p["value"] for p in data["observed"]]

    # Scale y to the observations and the model CENTRE lines, not the bands.
    # ARIMA's interval at n=7 is enormous — it can span negative cell counts — and
    # letting it drive the axis squashes the real data into an unreadable sliver.
    centres = [
        p["yhat"] for curve in data["curves"].values()
        for p in curve["points"] if p["yhat"] is not None
    ]
    low, high = min(centres + observed_values), max(centres + observed_values)
    pad = (high - low or abs(high) or 1) * 0.25
    y_range = [low - pad, high + pad]

    clipped = []
    for model, curve in data["curves"].items():
        points = curve["points"]
        days = [p["day"] for p in points]

        if curve["has_uncertainty"]:
            lower = [p["yhat_lower"] for p in points]
            upper = [p["yhat_upper"] for p in points]
            if any(v is not None and (v < y_range[0]) for v in lower) or \
               any(v is not None and (v > y_range[1]) for v in upper):
                clipped.append(model)

            figure.add_trace(go.Scatter(
                x=days + days[::-1], y=upper + lower[::-1],
                fill="toself", fillcolor=MODEL_COLORS[model], opacity=0.13,
                line=dict(width=0), hoverinfo="skip",
                name=f"{model} 95%", showlegend=False,
            ))

        figure.add_trace(go.Scatter(
            x=days, y=[p["yhat"] for p in points],
            mode="lines", name=model,
            line=dict(color=MODEL_COLORS[model], width=2),
        ))

    figure.add_trace(go.Scatter(
        x=observed_days, y=observed_values, mode="markers", name="observed",
        marker=dict(size=9, color="#e6e9ef", line=dict(width=1, color="#0b0e14")),
    ))

    # The flight itself: 3 days against a 289-day span, otherwise invisible.
    figure.add_vrect(x0=0, x1=3, fillcolor="#5aa9e6", opacity=0.15, line_width=0,
                     annotation_text="flight", annotation_font_size=10)
    figure.add_vline(x=max(observed_days), line_dash="dash", line_color="#6b7688",
                     annotation_text="last draw", annotation_font_size=10)

    figure.update_layout(
        template="plotly_dark", height=440,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="mission day (launch = 0, splashdown = 3)",
        yaxis_title=data["unit"],
        yaxis_range=y_range,
        legend=dict(orientation="h", y=1.12),
    )

    if clipped:
        # A clipped band looks NARROWER than it is, which would understate the
        # model's uncertainty. Say so rather than letting it mislead.
        figure.add_annotation(
            text=f"{' and '.join(clipped)} interval is clipped — it extends beyond the "
                 "plotted range and is <i>wider</i> than it appears",
            xref="paper", yref="paper", x=0, y=-0.22, showarrow=False,
            font=dict(size=11, color="#d8b968"),
        )
    return figure


def page_integration():
    st.header("Integration — rodent hits vs. human trajectories")

    # Non-dismissible, above everything. The framing has to land before any number.
    st.error(
        "**This is an evidence table, not a statistical integration.**\n\n"
        "Nothing on this page computes a correlation, enrichment, or hypothesis test "
        "linking rodent genes to human trajectories — and none could be computed "
        "honestly. The rodent data is mouse **skeletal muscle** (soleus, tibialis "
        "anterior); the Inspiration4 CBC panel is human **whole blood**. Those are not "
        "measurements of the same system. Add different species, different missions "
        "(RR-1 flew ~30+ days; Inspiration4 flew 3), and different measurement types — "
        "a DE gene is not a CBC analyte, and there is no row on which to join them.\n\n"
        "What follows is the ortholog status of the rodent hits, shown *beside* what "
        "each blood analyte tracks, for a human to reason about.",
        icon="🚫",
    )

    accession = st.selectbox("Rodent dataset", sorted(_abtest_accessions()))

    with st.spinner("Mapping orthologs…"):
        data = integrate_payload(accession)

    st.subheader("Ortholog mapping")
    st.caption(
        "Mouse–human orthology is a many-to-many graph, not a lookup table. Every gene "
        "is tagged; none is silently joined and **none is dropped** — a gene that "
        "vanished from this table would read as “not significant” rather than “not "
        "mappable”, which is a different and much worse claim."
    )

    # Same counts, same labels, same colours — CARDINALITY stays the single source
    # of truth and is passed in rather than duplicated inside the component.
    cardinality_counters(data["orthology"]["cardinality"], CARDINALITY)

    st.caption(f"Source: {data['orthology']['source']}")

    genes = pd.DataFrame(data["genes"])
    genes["human_orthologs"] = genes["human_symbols"].apply(
        lambda s: ", ".join(s) if s else "—"
    )
    genes["mapping"] = genes["cardinality"].map(lambda c: CARDINALITY[c][0])
    genes["trust"] = genes["cardinality"].map(TIER)

    tier = st.selectbox(
        "Show", ["all genes", "clean (1:1 only)", "ambiguous mappings", "not mappable"]
    )
    view = genes
    if tier == "clean (1:1 only)":
        view = view[view["cardinality"] == "one_to_one"]
    elif tier == "ambiguous mappings":
        view = view[view["cardinality"].isin(["one_to_many", "many_to_one", "many_to_many"])]
    elif tier == "not mappable":
        view = view[view["cardinality"] == "no_ortholog"]

    query = st.text_input("Filter by mouse gene, ENSMUSG, or human symbol", "")
    if query.strip():
        needle = query.strip().lower()
        view = view[
            view["mouse_symbol"].fillna("").str.lower().str.contains(needle)
            | view["ensembl_id"].str.lower().str.contains(needle)
            | view["human_orthologs"].str.lower().str.contains(needle)
        ]

    st.dataframe(
        view[["mouse_symbol", "ensembl_id", "log2fc", "padj", "mapping", "trust",
              "n_human", "human_orthologs"]],
        width="stretch",
        hide_index=True,
        column_config={
            "mouse_symbol": "Mouse gene",
            "ensembl_id": "ENSMUSG",
            "log2fc": st.column_config.NumberColumn("log2FC", format="%.3f"),
            "padj": st.column_config.NumberColumn("padj", format="%.2e"),
            "mapping": "Ortholog mapping",
            "trust": "Read as",
            "n_human": "Human genes",
            "human_orthologs": "Human ortholog(s)",
        },
    )
    st.caption(f"{len(view):,} of {len(genes):,} genes.")

    st.subheader("What the blood panel actually tracks")
    st.caption(data["cbc_context"]["note"])
    st.dataframe(
        pd.DataFrame(data["cbc_context"]["analytes"]),
        width="stretch", hide_index=True,
    )

    st.subheader("Caveats")
    for caveat in data["caveats"]:
        st.markdown(f"- {caveat}")


def page_methods():
    st.header("Methods")
    path = DOCS / "methods.md"
    if not path.is_file():
        st.error(f"docs/methods.md not found at {path}")
        return
    st.markdown(path.read_text(encoding="utf-8"))


# --- shell -------------------------------------------------------------------

PAGES = {
    "Study Explorer": page_study_explorer,
    "A/B Testing": page_abtest,
    "Forecasting": page_forecasting,
    "Integration": page_integration,
    "Methods": page_methods,
}

st.sidebar.title("🛰️ AstroOmix")
st.sidebar.caption("Space biology, two ways")
choice = st.sidebar.radio("Page", list(PAGES), label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption(
    "Rodent spaceflight A/B testing (NASA OSDR) and Inspiration4 molecular "
    "trajectories. All analysis code is shared with the FastAPI service — this is a "
    "UI, not a reimplementation."
)

PAGES[choice]()
