"""AstroOmix API.

Run locally:   uvicorn main:app --reload --port 8000   (from backend/)
Interactive:   http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from routers import abtest, forecast, integrate, studies

app = FastAPI(
    title="AstroOmix API",
    description="Space-biology platform: rodent A/B testing and Inspiration4 "
                "molecular trajectories.",
    version="0.1.0",
)

# TODO(before deploy): replace "*" with the Vercel frontend origin. A wildcard
# origin is fine for local development, but it lets any site on the internet call
# this API from a user's browser. Note that "*" is also incompatible with
# allow_credentials=True — the browser rejects that combination — which is why
# credentials stay off here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# A full DESeq2 result is ~22,700 genes. Uncompressed that is a ~3MB JSON body,
# which is slow over a free-tier dyno and heavy on Vercel's bandwidth — and large
# enough that Vite's dev proxy intermittently stalls on it. JSON of this shape
# compresses ~15x.
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(studies.router)
app.include_router(abtest.router)
app.include_router(forecast.router)
app.include_router(integrate.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
