# AstroOmix

Space-biology platform. Rodent spaceflight A/B testing (flight vs. ground) and
Inspiration4 human molecular trajectories, over real NASA OSDR data.

## Layout

    backend/     FastAPI + analysis code (deploys to Render)
      main.py            app, CORS, gzip
      routers/           /api/studies, /api/abtest/{accession}
      src/data/          OSDR loaders, mission-day axis
      src/abtest/        preprocess, DESeq2 (served), NB GLM (cross-check)
      config/            datasets.yaml
    frontend/    Vite + React (deploys to Vercel)
    docs/        DATA_NOTES.md — what the archive actually contains

## Run locally

Backend (from `backend/`):

    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
    # docs: http://localhost:8000/docs

Frontend (from `frontend/`):

    npm install
    npm run dev        # http://localhost:5173

The frontend calls the backend cross-origin in dev exactly as it will in prod
(`VITE_API_URL` in `.env.development`). There is deliberately **no dev proxy** —
see the comment in `vite.config.js`.

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET /api/health` | liveness |
| `GET /api/studies` | dataset catalogue from `config/datasets.yaml` |
| `GET /api/abtest/{accession}` | DESeq2 flight-vs-ground; `OSD-104`, `OSD-105` |

`/api/abtest` runs real DESeq2 (~15s cold) and caches the table to
`backend/data/cache/de/`, so repeat calls return in under a second. Pass
`?refresh=true` to re-run.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ALLOW_REFRESH` | `false` | Permits `?refresh=true` on `/api/abtest` and `/api/integrate`. |

**Do not set `ALLOW_REFRESH` on Render.** It defaults closed, and that default is a
safety limit rather than a preference: an uncached DESeq2 run peaks at **~2.4 GB**
of unique memory across ~18 worker processes, against a 512 MB free-tier cap. A
single `?refresh=true` in production does not make one request slow — it
OOM-kills the dyno and takes every endpoint down with it. Blocked requests return
**403**, never a silently-stale 200.

Locally, open the gate with a shell variable or a line in `.env`:

    ALLOW_REFRESH=true uvicorn main:app --reload --port 8000

(`src/env.py` deliberately never writes into `os.environ`, so `src/settings.py`
checks the shell first and then falls back to reading `.env` directly.)

`?refresh=true` on `/api/forecast` is deliberately **not** gated — an uncached
forecast peaks at ~236 MB, comfortably inside budget.

## Before deploying

* **Lock down CORS.** `main.py` allows `*`. Replace with the Vercel origin.
* Set `VITE_API_URL` on Vercel to the Render backend URL.
* Leave `ALLOW_REFRESH` unset (see above).
* The pre-warmed caches in `backend/data/cache/{de,forecast,integrate}/` are
  committed and are **load-bearing, not just a latency win** — they are what keeps
  DESeq2 from ever running in production. Do not delete them.
* Render free-tier dynos sleep; the first request after idle pays dyno wake-up.

## Status

Working end to end: Study Explorer, A/B Testing (volcano + sortable hits table),
Methods. Forecasting and Integration are honest placeholders — the endpoints do
not exist yet, and mocked charts would be worse than empty pages.

Read `docs/DATA_NOTES.md` before adding datasets. Several plausible-looking
accessions do not contain what their titles suggest.
