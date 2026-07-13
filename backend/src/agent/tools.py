"""Tools the Research Assistant may call.

Every tool is a thin wrapper over an existing, already-tested function. Nothing
here computes a forecast, a fold change, or an ortholog mapping — if a number
reaches the agent, it was produced by the same code path that produces the
numbers on the pages.

The hard rule
-------------
Tool results carry the caveats *with* the data, deliberately. `get_forecast`
returns `best_by_mae_warning`, `flat_extrapolation`, `has_uncertainty`,
`n_timepoints` and `last_observed_day` alongside the metrics — not because the
agent needs them to answer, but because it cannot enforce a caveat it was never
shown. Stripping the warnings to save tokens would leave the model free to say
"LightGBM is the best model, so trust its day-300 number", which is exactly
backwards and exactly what this design prevents.
"""

from __future__ import annotations

import json
import warnings

from routers.abtest import _cached_results, _to_records
from routers.forecast import _build, _cache_path, _valid_analytes, _valid_crew
from routers.studies import load_studies
from src.forecast.common import MISSION_DURATION_DAYS

# --- forecasting -------------------------------------------------------------


def list_analytes() -> dict:
    """The 20 real CBC analytes and the crew ids the forecast accepts."""
    return {
        "analytes": _valid_analytes(),
        "crew": _valid_crew(),
        "n_analytes": len(_valid_analytes()),
        "note": (
            "These are the only analytes that exist. The Inspiration4 CBC panel is "
            "the ONLY modality with post-return recovery timepoints; the I4 RNA-seq "
            "stops at R+1."
        ),
    }


def get_forecast(analyte: str, crew: str = "mean", extra_days: int = 0) -> dict:
    """Real Prophet / ARIMA / LightGBM output for one CBC analyte.

    Returns the observed points, the LOO-CV metrics, best_by_mae, the
    best_by_mae_warning, and the what-if with its flat_extrapolation flags.
    """
    analytes = _valid_analytes()
    if analyte not in analytes:
        return {"error": f"{analyte!r} is not a CBC analyte.", "valid_analytes": analytes}

    crews = _valid_crew()
    if crew not in crews:
        return {"error": f"{crew!r} is not valid.", "valid_crew": crews}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        path = _cache_path(analyte, crew, extra_days)
        payload = (
            json.loads(path.read_text()) if path.is_file()
            else _build(analyte, crew, extra_days)
        )

    observed = payload["observed"]
    last_day = max(point["day"] for point in observed)

    # The dense model curves (~80 points x 3 models) are omitted: they are for
    # plotting, and shipping them would crowd out the caveats in the context. The
    # observed points and the what-if — the things a claim can be grounded in —
    # are kept in full.
    return {
        "analyte": payload["analyte"],
        "unit": payload["unit"],
        "crew": payload["crew"],
        "n_timepoints": payload["n_timepoints"],
        "n_crew": 4,
        "observed": observed,
        "last_observed_day": last_day,
        "mission_day_axis": (
            "launch = day 0, splashdown = day "
            f"{MISSION_DURATION_DAYS}. Negative days are pre-flight. R+1 is day "
            f"{MISSION_DURATION_DAYS + 1}, NOT day 1."
        ),
        "comparison": payload["comparison"],  # metrics, best_by_mae, best_by_mae_warning
        "model_uncertainty": {
            name: curve["has_uncertainty"] for name, curve in payload["curves"].items()
        },
        "whatif": payload["whatif"],  # carries flat_extrapolation + caveat per model
        "caveat": payload["caveat"],
    }


# --- differential expression -------------------------------------------------


def list_studies_tool() -> dict:
    """The datasets in the project, from config/datasets.yaml."""
    return {"studies": load_studies()}


def get_de_results(accession: str, top_n: int = 20) -> dict:
    """Real DESeq2 flight-vs-ground results for a rodent accession."""
    from routers.abtest import _abtest_accessions

    allowed = sorted(_abtest_accessions())
    if accession not in allowed:
        return {"error": f"{accession!r} is not an A/B dataset.", "valid": allowed}

    results = _cached_results(accession)
    significant = int((results["padj"] < 0.05).sum())
    records = _to_records(results)

    top = [r for r in records if r["padj"] is not None][: max(1, min(top_n, 100))]

    return {
        "accession": accession,
        "method": "DESeq2 (pydeseq2)",
        "contrast": "flight vs ground",
        "n_genes_tested": len(records),
        "n_significant_fdr_0.05": significant,
        "design": "6 flight vs 6 ground control",
        "top_genes_by_padj": top,
        "caveat": (
            "n = 6 per group. Genes with a null padj were dropped by DESeq2's "
            "independent filtering — that is 'no result', not 'not significant'. "
            "Positive log2fc means higher expression in flight."
        ),
    }


# --- schemas -----------------------------------------------------------------

TOOLS = [
    {
        "name": "list_analytes",
        "description": (
            "List the 20 real Inspiration4 CBC analytes and the valid crew ids. "
            "Call this first when a question spans multiple blood markers, so you "
            "reason over the analytes that actually exist rather than guessing names."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forecast",
        "description": (
            "Get the REAL computed forecast for one CBC analyte: the observed "
            "timepoints, the leave-one-out CV metrics (MAE/RMSE/MAPE) for Prophet, "
            "ARIMA and LightGBM, which model wins by MAE, and the what-if "
            "extrapolation. Call this for ANY question about a blood marker's "
            "trajectory, recovery, model quality, or a future prediction — never "
            "answer such a question from memory. The result carries the honesty "
            "flags (best_by_mae_warning, flat_extrapolation) and you must surface "
            "them when they are set."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analyte": {
                    "type": "string",
                    "description": "A CBC analyte name, e.g. 'absolute_neutrophils'.",
                },
                "crew": {
                    "type": "string",
                    "description": "'mean' (across all 4 crew) or a crew id. Default 'mean'.",
                },
                "extra_days": {
                    "type": "integer",
                    "description": (
                        "Days past the last observed draw to extrapolate. 0 for no "
                        "what-if. The last real draw is mission day 197."
                    ),
                },
            },
            "required": ["analyte"],
        },
    },
    {
        "name": "list_studies",
        "description": "List the datasets in the project with their organism, tissue and design.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_de_results",
        "description": (
            "Get the REAL DESeq2 flight-vs-ground differential expression results "
            "for a rodent accession (OSD-104 = soleus, OSD-105 = tibialis anterior). "
            "Call this for any question about rodent genes, fold changes, or which "
            "genes respond to spaceflight."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "accession": {"type": "string", "description": "OSD-104 or OSD-105."},
                "top_n": {
                    "type": "integer",
                    "description": "How many top genes by FDR to return (max 100).",
                },
            },
            "required": ["accession"],
        },
    },
]

DISPATCH = {
    "list_analytes": list_analytes,
    "get_forecast": get_forecast,
    "list_studies": list_studies_tool,
    "get_de_results": get_de_results,
}


def run_tool(name: str, arguments: dict) -> dict:
    """Execute a tool. Errors are returned as data, not raised — the agent should
    see and report a failure, not have the page crash under it."""
    function = DISPATCH.get(name)
    if function is None:
        return {"error": f"Unknown tool {name!r}."}
    try:
        return function(**arguments)
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {error}"}
