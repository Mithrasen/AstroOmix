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

## Before deploying

* **Lock down CORS.** `main.py` allows `*`. Replace with the Vercel origin.
* Set `VITE_API_URL` on Vercel to the Render backend URL.
* Render free-tier dynos sleep; the first request after idle will be slow, on top
  of the ~15s cold DESeq2 run. The disk cache does not survive a restart.

## Status

Working end to end: Study Explorer, A/B Testing (volcano + sortable hits table),
Methods. Forecasting and Integration are honest placeholders — the endpoints do
not exist yet, and mocked charts would be worse than empty pages.

Read `docs/DATA_NOTES.md` before adding datasets. Several plausible-looking
accessions do not contain what their titles suggest.
