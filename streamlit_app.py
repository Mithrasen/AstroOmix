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
from src.forecast.reliability import assess  # noqa: E402
from src.integrate.cross_reference import cross_reference  # noqa: E402
from src.settings import allow_refresh  # noqa: E402
from src.ui.components import (  # noqa: E402
    animated_counters,
    cardinality_counters,
    mission_timeline,
)
from src.ui.assistant_embed import (  # noqa: E402
    DE_CHIPS,
    FORECAST_CHIPS,
    render_embedded,
    render_popout,
)
from src.ui.home import render as render_home  # noqa: E402
from src.ui.icons import logo  # noqa: E402
from src.ui import methods_page  # noqa: E402
from src.ui.theme import inject_theme  # noqa: E402
from src.upload.analyse import ENGINES, run_de, run_forecast  # noqa: E402
from src.upload.validate import (  # noqa: E402
    MAX_COUNTS_BYTES,
    MAX_GENES,
    MAX_RUNS_PER_SESSION,
    MAX_SAMPLES,
    MAX_SERIES_BYTES,
    UploadError,
    check_rate_limit,
    record_run,
    validate_counts,
    validate_design,
    validate_series,
)

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


UPLOAD_BANNER = (
    "**You are viewing results from your own uploaded data.** This has not been "
    "validated the way OSD-104 / OSD-105 have — nobody has checked that the counts "
    "mean what you think they mean, that the design is correct, or that the result "
    "is biologically sensible. Results are **not cached** and are not saved."
)


def upload_abtest():
    """'Upload your own data' — additive. The OSD-104/105 flow above is untouched."""
    st.markdown(
        '<div class="mc-rule"><strong>Analyse your own data</strong></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "A co-equal path, not an afterthought. OSD-104/105 are the built-in "
        "example; your counts run the same pipeline and get the same caveats."
    )
    with st.container(border=True):
        st.caption(
            f"Counts CSV: genes as rows (first column = gene ID), samples as columns. "
            f"Hosted-demo limits: {MAX_COUNTS_BYTES // 1024 // 1024} MB, "
            f"{MAX_GENES:,} genes, {MAX_SAMPLES} samples. Sample columns must carry "
            "`_FLT_` or `_GC_`, or supply a design CSV (sample, group)."
        )

        # The engine gate is unchanged — only what is SHOWN. The memory rationale
        # and the dispersion methodology are implementation reasoning; they belong
        # in Methods, not in the middle of someone's workflow.
        available = [
            key for key, engine in ENGINES.items()
            if not engine["requires_allow_refresh"] or allow_refresh()
        ]
        engine = available[0]
        if len(available) > 1:
            engine = st.selectbox(
                "Engine", available, format_func=lambda k: ENGINES[k]["label"],
                key="ab_engine",
            )


        counts_file = st.file_uploader("Counts CSV", type=["csv"], key="ab_counts")
        design_file = st.file_uploader(
            "Design CSV (optional — only if sample names lack _FLT_/_GC_)",
            type=["csv"], key="ab_design",
        )

        used = st.session_state.get("ab_runs", 0)
        st.caption(f"Runs used this session: {used} / {MAX_RUNS_PER_SESSION}")

        if not st.button("Run differential expression", key="ab_run"):
            return
        if counts_file is None:
            st.error("Upload a counts CSV first.")
            return

        try:
            check_rate_limit(st.session_state, "ab_runs")
            counts, groups = validate_counts(counts_file.getvalue())
            if design_file is not None:
                groups = validate_design(design_file.getvalue(), counts)
        except UploadError as error:
            # Surfaced verbatim — the validators' messages are the real diagnosis.
            st.error(str(error))
            return

        record_run(st.session_state, "ab_runs")

        with st.spinner(f"Running {ENGINES[engine]['label']} on your data…"):
            try:
                results = run_de(counts, engine=engine)
            except Exception as error:
                st.error(f"The analysis failed on your data: {error}")
                return

        st.warning(UPLOAD_BANNER, icon="⚠️")

        n_significant = int((results["padj"] < 0.05).sum())
        animated_counters([
            {"label": "Genes tested", "value": int(results["pvalue"].notna().sum())},
            {"label": "FDR < 0.05", "value": n_significant, "color": "#4ec9a0"},
            {"label": "Engine", "text": ENGINES[engine]["label"], "color": "#d8b968"},
        ])

        # The uploaded matrix's index name comes from the user's CSV header, so
        # normalise it rather than guessing what they called it.
        display = results.rename_axis("gene").reset_index()
        st.plotly_chart(volcano(display), width="stretch")
        st.dataframe(
            display.sort_values("padj", na_position="last"),
            width="stretch", hide_index=True,
            column_config={
                "base_mean": st.column_config.NumberColumn("Base mean", format="%.1f"),
                "log2fc": st.column_config.NumberColumn("log2FC", format="%.3f"),
                "pvalue": st.column_config.NumberColumn("p-value", format="%.2e"),
                "padj": st.column_config.NumberColumn("padj (FDR)", format="%.2e"),
            },
        )


def page_abtest():
    """Upload first. The built-in study is an EXAMPLE, revealed on click."""
    st.header("Differential Expression")
    st.caption(
        "Flight versus ground control. Your counts are the primary path; the "
        "rodent spaceflight studies below are worked examples."
    )

    render_popout(
        "de",
        "Scoped to this comparison. It calls the same results you see below, and "
        "every figure it states is verified against them before you see it.",
        DE_CHIPS,
    )

    upload_abtest()

    st.write("")
    st.markdown('<div class="mc-rule"><strong>See a worked example</strong></div>',
                unsafe_allow_html=True)

    catalogue = {s["accession"]: s for s in studies() if s["module"] == "abtest"}
    columns = st.columns(len(catalogue) + 1)
    for index, accession in enumerate(sorted(catalogue)):
        with columns[index]:
            tissue = catalogue[accession]["tissue"]
            if st.button(f"Open {accession} — {tissue}", key=f"ex_{accession}",
                         width="stretch"):
                st.session_state["de_example"] = accession
                st.rerun()
    with columns[-1]:
        if st.session_state.get("de_example") and st.button(
            "Close example", key="ex_close", width="stretch"
        ):
            st.session_state.pop("de_example")
            st.rerun()

    chosen = st.session_state.get("de_example")
    if chosen:
        abtest_report(chosen, catalogue)


def abtest_report(accession: str, catalogue: dict):
    """The built-in study's full report. Identical to what it always was."""
    force = st.checkbox(
        "Force refresh (re-run DESeq2)",
        value=False,
        key=f"force_{accession}",
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


def upload_forecast():
    """'Upload your own time series' — additive. The CBC flow above is untouched."""
    st.markdown(
        '<div class="mc-rule"><strong>Analyse your own time series</strong></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "A co-equal path, not an afterthought. The Inspiration4 CBC panel is the "
        "built-in example; your series runs the same models, the same LOO-CV, and "
        "the same reliability tiers."
    )
    with st.container(border=True):
        st.caption(
            f"CSV with a `day` and a `value` column (a group/crew column is ignored "
            f"for now). `day` must already be a numeric mission day, not a raw "
            f"'L-92'/'R+1' label. Hosted-demo limit: "
            f"{MAX_SERIES_BYTES // 1024 // 1024} MB; minimum 3 timepoints."
        )

        series_file = st.file_uploader("Series CSV", type=["csv"], key="fc_series")
        extra_days = st.number_input(
            "Exploratory horizon: days past your last point",
            min_value=0, max_value=365, value=30, step=1, key="fc_extra",
        )

        used = st.session_state.get("fc_runs", 0)
        st.caption(f"Runs used this session: {used} / {MAX_RUNS_PER_SESSION}")

        if not st.button("Fit models", key="fc_run"):
            return
        if series_file is None:
            st.error("Upload a series CSV first.")
            return

        try:
            check_rate_limit(st.session_state, "fc_runs")
            series, _ = validate_series(series_file.getvalue())
        except UploadError as error:
            st.error(str(error))
            return

        record_run(st.session_state, "fc_runs")

        with st.spinner("Fitting Prophet, ARIMA and LightGBM on your series…"):
            try:
                data = run_forecast(series, int(extra_days))
            except Exception as error:
                st.error(f"The fit failed on your data: {error}")
                return

        st.warning(
            "**You are viewing results from your own uploaded time series.** This has "
            "not been validated the way the Inspiration4 CBC panel has, and results "
            "are **not cached**.",
            icon="⚠️",
        )
        render_forecast(data, int(extra_days))


def page_forecasting():
    """Upload first. The Inspiration4 panel is an EXAMPLE, revealed on click."""
    st.header("Longitudinal Analysis")
    st.caption(
        "How a marker moves across a mission. Your time series is the primary path; "
        "the Inspiration4 crew blood panel below is a worked example."
    )

    render_popout(
        "forecast",
        "Scoped to this analysis. It reads the same fits and scores you see below, "
        "and it will tell you when a model reconstructs the observed points well "
        "but cannot forecast.",
        FORECAST_CHIPS,
    )

    upload_forecast()

    st.write("")
    st.markdown('<div class="mc-rule"><strong>See a worked example</strong></div>',
                unsafe_allow_html=True)

    left, right = st.columns([2, 1])
    with left:
        st.caption(
            "The SpaceX Inspiration4 crew blood panel — 4 crew, 7 timepoints, "
            "from pre-launch through months of recovery."
        )
    with right:
        if not st.session_state.get("fc_example"):
            if st.button("Open the Inspiration4 example", key="fc_open",
                         width="stretch"):
                st.session_state["fc_example"] = True
                st.rerun()
        elif st.button("Close example", key="fc_close", width="stretch"):
            st.session_state.pop("fc_example")
            st.rerun()

    if st.session_state.get("fc_example"):
        forecast_report()


def forecast_report():
    """The built-in CBC report. Identical to what it always was."""
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
            "Exploratory horizon: days past last draw", min_value=0, max_value=365, value=30, step=1,
        )

    with st.spinner("Fitting models…"):
        data = forecast_payload(analyte, crew, int(extra_days))

    render_forecast(data, int(extra_days))


def render_forecast(data: dict, extra_days: int):
    """Chart + LOO table + what-if. Shared by the CBC flow and the upload flow, so
    the warnings and caveats are guaranteed identical for both."""

    # Graduated by sample size, BEFORE any number is shown. A hard floor at 3 points
    # is not enough: 3 points is fittable, not trustworthy, and the models will
    # happily draw a confident-looking curve on it.
    grade = assess(data["n_timepoints"], data["comparison"]["metrics"])
    n = data["n_timepoints"]
    best = data["comparison"]["best_by_mae"]
    warning = data["comparison"].get("best_by_mae_warning")

    # Three levels of disclosure, not five repetitions of one point. Every caveat
    # is still here — the n=4x7 note, the reliability reasons, the LOO
    # reconstruction/extrapolation distinction, the lowest-MAE trap — but each is
    # said ONCE and the detail is gathered under one expander. Said five times it
    # reads as anxious; said once, well, it lands harder.

    # (1) persistent badge
    st.markdown(
        f'<span class="badge">Exploratory · {n} timepoints</span>',
        unsafe_allow_html=True,
    )

    # (2) ONE prominent warning
    if grade["tier"] == "critical":
        st.error(f"**{grade['headline']}**", icon="🚫")
    else:
        st.warning(
            "**This dataset supports descriptive trajectory comparison, not "
            "validated future prediction.**",
            icon="⚠️",
        )

    # (3) all the detail, once, in one place
    with st.expander("Why this is limited"):
        for reason in grade["reasons"]:
            st.markdown(f"- {reason}")
        st.markdown(f"- {data['caveat']}")
        st.markdown(
            f"- Leave-one-out cross-validation holds out each of the {n} timepoints "
            "once and fits on the rest. It measures how well a model "
            "**reconstructs the observed points** — it does **not** validate the "
            "exploratory horizon."
        )
        if warning:
            st.markdown(
                f"- **“Lowest MAE” does not mean “best forecaster.”** {warning}"
            )

    st.plotly_chart(trajectory(data), width="stretch")

    st.subheader("Model comparison — leave-one-out CV")

    label = {"lightgbm": "LightGBM", "prophet": "Prophet", "arima": "ARIMA"}.get(
        best, str(best)
    )
    st.markdown(
        f"**Lowest leave-one-out MAE:** :{'red' if warning else 'green'}[{label}]"
    )
    st.caption(
        "This measures reconstruction of observed points, not forecasting ability."
    )

    metrics = pd.DataFrame(data["comparison"]["metrics"]).T.reset_index()
    metrics.columns = ["model", "MAE", "RMSE", "MAPE %", "folds", "failed"]
    metrics["uncertainty"] = metrics["model"].map(
        lambda m: "95% interval" if data["curves"][m]["has_uncertainty"]
        else "no uncertainty estimate"
    )
    st.dataframe(metrics, width="stretch", hide_index=True)

    if data.get("whatif"):
        st.subheader(f"Exploratory horizon: {int(extra_days)} days past the last draw")
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
    # No assistant here. Methods is a reference page — it already states plainly
    # what a reader would otherwise have to ask, and the assistant belongs where
    # there is a computed result to interrogate.
    methods_page.render()


# --- shell -------------------------------------------------------------------

def goto(page: str) -> None:
    """Route to a page.

    "page" is NOT owned by any widget, so it can be written directly. The earlier
    sidebar version wrote a radio's key after the radio existed, which Streamlit
    rejects with StreamlitAPIException — that whole class of bug is gone with the
    sidebar.
    """
    st.session_state["page"] = page
    st.rerun()


PAGES = {
    "Home": lambda: render_home(goto),
    "Differential Expression": page_abtest,
    "Longitudinal Analysis": page_forecasting,
    "Methods": page_methods,
}

NAV = ["Differential Expression", "Longitudinal Analysis", "Methods"]

if "page" not in st.session_state:
    st.session_state["page"] = "Home"

current = st.session_state["page"]
if current not in PAGES:
    current = "Home"

# --- header bar: wordmark left, nav right. No sidebar. --------------------
brand, spacer, *nav_slots = st.columns([2.6, 0.4] + [1.3] * len(NAV))

with brand:
    # The mark IS the home button. Streamlit cannot make injected HTML clickable,
    # so a real button is laid over the mark and stripped of every visual (see
    # .st-key-nav_home in theme.py): what you see is the logo, what you click is a
    # button. That removes the separate "Home" nav item — a wordmark that goes home
    # is a convention every user already knows, and it does not need a tab.
    st.markdown(
        f'<div class="logo">{logo(46)}<span class="logo-text">'
        f'Astro<span class="logo-omix">Omix</span></span></div>',
        unsafe_allow_html=True,
    )
    # The label still exists for screen readers; it is only visually transparent.
    if st.button("Home", key="nav_home"):
        goto("Home")

for slot, name in zip(nav_slots, NAV):
    with slot:
        if st.button(
            name,
            key=f"nav_{name}",
            width="stretch",
            type="primary" if current == name else "secondary",
        ):
            goto(name)
st.markdown('<div class="appbar"></div>', unsafe_allow_html=True)

PAGES[current]()
