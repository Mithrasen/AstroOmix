"""GET /api/studies — the datasets AstroOmix actually uses."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["studies"])

CONFIG = Path(__file__).resolve().parents[1] / "config" / "datasets.yaml"


@lru_cache(maxsize=1)
def load_studies() -> list[dict]:
    with CONFIG.open() as handle:
        return yaml.safe_load(handle)["studies"]


@router.get("/studies")
def list_studies() -> dict:
    """Static catalogue, read from config/datasets.yaml."""
    return {"studies": load_studies()}
