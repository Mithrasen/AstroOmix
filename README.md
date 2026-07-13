# AstroOmix

**Live demo:** [astroomix.streamlit.app](https://astroomix.streamlit.app/)

AstroOmix is a research web app for analysing space-biology data. It runs two
workflows over real NASA datasets — bulk RNA-seq differential expression (rodent
spaceflight vs. matched ground control) and longitudinal modelling of human
biosignals across a mission — and pairs them with an AI research assistant that is
constrained to the computed results. The assistant has no independent knowledge of
these datasets: it calls the same analysis code the pages run, every tool call it
makes is shown to you, and **every figure in its answers is verified against the
actual tool output before you see it.** Anything that cannot be traced is withheld
rather than shown. It also retrieves real published papers from PubMed — retrieval
only, displayed with their abstracts for you to judge, never presented as validation
of a result.

Space-biology datasets are small, heterogeneous, and easy to overinterpret. The
point of this project is not to squeeze more confidence out of them than they can
support; it is to make the limits of the data visible while the analysis is being
read.

## What it does

| Workflow | What it is |
|---|---|
| Differential expression | Flight vs. ground control on bulk RNA-seq. PyDESeq2 for the worked examples; a resource-safe NB-GLM for uploaded data. Benjamini–Hochberg FDR. |
| Longitudinal analysis | Prophet / ARIMA / LightGBM compared by leave-one-out CV on a repeated-measures blood panel. Illustrative comparison, not a model recommendation. |
| Research assistant | Tool-based, runtime-verified, able to abstain. Requires an Anthropic API key. |
| Literature retrieval | Real PubMed records via NCBI E-utilities, with abstracts shown. Retrieval, not validation. |

Honesty is enforced in code, not just claimed in copy:

* **Numbers are verified at runtime.** Every figure in an assistant answer must
  trace to a tool result, a difference between two tool results, or a structural
  constant. Everything else is withheld — in the deployed app, on every response,
  not only in the test suite.
* **Citations are verified the same way.** A PMID that no literature tool returned
  is withheld exactly as a fabricated number is.
* **Retrieval is never dressed as validation.** "Computation: verified" and
  "Literature: retrieved" are two separate badges and are never merged into one.
* **Thin data is flagged, not modelled around.** The longitudinal panel has seven
  timepoints; the app says so, and says what that does and does not support.

Read [docs/METHODS.md](docs/METHODS.md) for the methods and their limitations.

## Run it locally

Requires Python 3.12.

```bash
git clone https://github.com/Mithrasen/AstroOmix.git
cd AstroOmix
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The two analysis workflows run without any API key — the pre-warmed caches in
`backend/data/cache/` mean DESeq2 and the forecast fits do not have to run on first
load.

### The AI assistant needs an Anthropic API key

Without one, the analysis pages work normally and the assistant shows a "not
configured" notice instead of failing. To enable it, create a `.env` file in the
repo root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is git-ignored. The key is **never** read from the ambient environment —
only from `.env` locally, or from Streamlit secrets when deployed. Get a key at
[console.anthropic.com](https://console.anthropic.com/).

## Deploying to Streamlit Community Cloud

`streamlit_app.py` and `requirements.txt` are at the repo root, which is where
Cloud looks for them. After pointing Cloud at the repo, add the key under
**App settings → Secrets**:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Key resolution is `st.secrets` → `.env` → not configured, so the same code works
deployed and locally.

## Data

Real NASA Open Science Data Repository studies — rodent spaceflight muscle
(OSD-104 soleus, OSD-105 tibialis anterior; 6 flight vs. 6 ground) and the
Inspiration4 civilian mission blood panel (4 crew, 7 timepoints). Mouse–human
orthology comes from MGI. Nothing is simulated, and no per-astronaut clinical
measure is stubbed in where the public data does not have one.

[docs/DATA_NOTES.md](docs/DATA_NOTES.md) is worth reading before you add a dataset:
several plausible-looking accessions do not contain what their titles suggest.

## Layout

```
streamlit_app.py        the app (Streamlit Cloud entry point)
requirements.txt        -> backend/requirements.txt
backend/
  src/data/             OSDR loaders, mission-day axis
  src/abtest/           preprocessing, DESeq2, NB-GLM cross-check
  src/forecast/         Prophet / ARIMA / LightGBM, LOO-CV, reliability tiers
  src/integrate/        MGI mouse-human orthology (bipartite, cardinality-aware)
  src/literature/       PubMed retrieval via NCBI E-utilities
  src/agent/            the assistant: tools, key resolution, grounding guard
  src/ui/               theme, cards, the embedded assistant
  routers/              HTTP handlers; the app imports their plain functions
  tests/                189 tests
docs/                   METHODS.md, DATA_NOTES.md
```

`backend/data/cache/` is committed on purpose and is load-bearing: it is what keeps
a 2.4 GB DESeq2 run from ever happening on a hosted dyno.

## Limitations

Spaceflight cohorts are tiny, so results here are descriptive and
hypothesis-generating. Nothing in this app is diagnostic or a basis for a health
decision. Cross-species links are evidence for a human to weigh, not a statistical
result. Retrieved literature is a search result, not proof of anything.

## Licence

MIT.
