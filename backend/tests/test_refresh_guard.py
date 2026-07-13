"""The refresh gate must default CLOSED.

This is not a style preference. An uncached DESeq2 run peaks at ~2.4 GB of unique
memory across ~18 worker processes; Render's free tier caps at 512 MB. So
`?refresh=true` in production does not make one request slow — it OOM-kills the
dyno and takes every endpoint down with it. `refresh` is the single public
parameter that can defeat the committed cache, so it is gated.
"""

import pytest
from fastapi.testclient import TestClient

import src.settings as settings
from main import app
from src.refresh_guard import enforce_refresh_allowed
from src.settings import allow_refresh

client = TestClient(app)

GATED = [
    "/api/abtest/OSD-104",
    "/api/integrate/OSD-104",
]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Neutralise both flag sources.

    `_flag` reads os.environ and then falls back to the .env file. A developer
    with ALLOW_REFRESH=true in their own .env would otherwise make these tests
    pass for the wrong reason — and this test is the only thing standing between
    production and an OOM.
    """
    monkeypatch.delenv("ALLOW_REFRESH", raising=False)
    monkeypatch.setattr(settings, "load_env", lambda *a, **k: {})


# --- default closed ---------------------------------------------------------

def test_allow_refresh_defaults_to_false():
    assert allow_refresh() is False


@pytest.mark.parametrize("path", GATED)
def test_refresh_true_is_403_when_unset(path):
    response = client.get(path, params={"refresh": "true"})
    assert response.status_code == 403
    assert "refresh is disabled" in response.json()["detail"]


@pytest.mark.parametrize("path", GATED)
def test_refresh_true_is_403_when_explicitly_false(monkeypatch, path):
    monkeypatch.setenv("ALLOW_REFRESH", "false")
    response = client.get(path, params={"refresh": "true"})
    assert response.status_code == 403


@pytest.mark.parametrize("value", ["", "0", "no", "False", "TRUE_ISH", "1"])
def test_only_the_exact_string_true_opens_the_gate(monkeypatch, value):
    """A safety limit must not be opened by a typo or a truthy-looking value."""
    monkeypatch.setenv("ALLOW_REFRESH", value)
    assert allow_refresh() is False


# --- fails LOUDLY, not silently ---------------------------------------------

@pytest.mark.parametrize("path", GATED)
def test_blocked_refresh_does_not_silently_serve_the_cache(path):
    """Silently ignoring the flag would be miserable to debug: you would edit an
    analysis, request refresh, get a stale table, and get no signal that your
    change never ran. It must be a 403, not a 200."""
    response = client.get(path, params={"refresh": "true"})
    assert response.status_code == 403
    assert response.status_code != 200


# --- the normal path is untouched -------------------------------------------

@pytest.mark.parametrize("path", GATED)
def test_requests_without_refresh_still_work(path):
    """The gate must not break ordinary cached reads — that is every real request."""
    response = client.get(path)
    assert response.status_code == 200


def test_forecast_refresh_is_NOT_gated(monkeypatch):
    """Deliberate asymmetry: an uncached forecast peaks at ~236 MB, inside the
    512 MB budget, so it is not a hazard and stays available."""
    response = client.get(
        "/api/forecast/hemoglobin",
        params={"crew": "mean", "extra_days": 30, "refresh": "true"},
    )
    assert response.status_code == 200


# --- the gate opens when it should ------------------------------------------

def test_gate_opens_with_allow_refresh_true(monkeypatch):
    monkeypatch.setenv("ALLOW_REFRESH", "true")
    assert allow_refresh() is True
    # Does not raise. (We do not drive the endpoint here — that would run the
    # 2.4 GB DESeq2 path this whole module exists to prevent.)
    enforce_refresh_allowed(True)


def test_dotenv_fallback_can_open_the_gate(monkeypatch):
    """`env.py` never writes into os.environ, so a .env-only value would be
    invisible without the fallback. Local workflow depends on it."""
    monkeypatch.delenv("ALLOW_REFRESH", raising=False)
    monkeypatch.setattr(settings, "load_env", lambda *a, **k: {"ALLOW_REFRESH": "true"})
    assert allow_refresh() is True


def test_shell_env_beats_dotenv(monkeypatch):
    """A committed .env must never override a Render dashboard setting."""
    monkeypatch.setenv("ALLOW_REFRESH", "false")
    monkeypatch.setattr(settings, "load_env", lambda *a, **k: {"ALLOW_REFRESH": "true"})
    assert allow_refresh() is False
