"""Key resolution: st.secrets → .env → None. Never os.environ.

The bug this pins: `.env` is git-ignored, so it does NOT exist on Streamlit Cloud.
An agent that only reads `.env` finds no key in production and fails there while
working perfectly on the developer's machine — the same environment-mismatch shape
that made the Render deploys hard to debug.
"""

import os

import pytest

import src.agent.keys as keys
from src.agent.keys import NOT_CONFIGURED_MESSAGE, resolve_api_key

SENTINEL = "sk-ant-AMBIENT-MUST-NEVER-BE-USED"


@pytest.fixture(autouse=True)
def poison_the_ambient_environment(monkeypatch):
    """Put a key in os.environ for EVERY test in this module.

    If any resolution path ever reads the ambient environment, these tests fail.
    That environment is shared with Claude Code's own billing and auth — reading a
    key from it could silently bill the wrong account. env.py's rule stands.
    """
    monkeypatch.setitem(os.environ, "ANTHROPIC_API_KEY", SENTINEL)


# --- never os.environ --------------------------------------------------------

def test_key_is_never_read_from_the_ambient_environment(monkeypatch):
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: None)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: None)

    resolution = resolve_api_key()
    assert resolution.key != SENTINEL
    assert resolution.key is None
    assert resolution.configured is False
    assert resolution.source == "none"


# --- resolution order --------------------------------------------------------

def test_streamlit_secrets_wins(monkeypatch):
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: "sk-ant-from-secrets")
    monkeypatch.setattr(keys, "_from_dotenv", lambda: "sk-ant-from-dotenv")

    resolution = resolve_api_key()
    assert resolution.key == "sk-ant-from-secrets"
    assert resolution.source == "streamlit_secrets"


def test_falls_back_to_dotenv_when_no_secrets(monkeypatch):
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: None)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: "sk-ant-from-dotenv")

    resolution = resolve_api_key()
    assert resolution.key == "sk-ant-from-dotenv"
    assert resolution.source == "dotenv"


def test_no_key_anywhere_is_a_normal_state_not_a_crash(monkeypatch):
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: None)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: None)

    resolution = resolve_api_key()  # must not raise
    assert resolution.configured is False
    assert "requires an API key" in NOT_CONFIGURED_MESSAGE


# --- st.secrets must degrade gracefully -------------------------------------

def test_missing_secrets_file_does_not_raise(monkeypatch):
    """st.secrets RAISES when no secrets.toml exists — the common local case. That
    exception must not propagate, or a developer whose key is in .env loses the
    page entirely."""
    class Exploding:
        def __getitem__(self, _):
            raise FileNotFoundError("No secrets file found")

    import streamlit

    monkeypatch.setattr(streamlit, "secrets", Exploding(), raising=False)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: "sk-ant-from-dotenv")

    resolution = resolve_api_key()  # must not raise
    assert resolution.key == "sk-ant-from-dotenv"


def test_secrets_present_but_key_absent_falls_through(monkeypatch):
    import streamlit

    monkeypatch.setattr(streamlit, "secrets", {}, raising=False)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: "sk-ant-from-dotenv")

    assert resolve_api_key().key == "sk-ant-from-dotenv"


def test_blank_key_is_treated_as_absent(monkeypatch):
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: None)
    monkeypatch.setattr(keys, "_from_dotenv", lambda: None)

    import streamlit

    monkeypatch.setattr(streamlit, "secrets", {"ANTHROPIC_API_KEY": "   "}, raising=False)
    assert resolve_api_key().configured is False


def test_missing_dotenv_file_does_not_raise(monkeypatch):
    """load_env raises FileNotFoundError with no .env — the deployed-Cloud case."""
    def explode(*a, **k):
        raise FileNotFoundError("no .env")

    monkeypatch.setattr(keys, "load_env", explode)
    monkeypatch.setattr(keys, "_from_streamlit_secrets", lambda: None)

    resolution = resolve_api_key()  # must not raise
    assert resolution.configured is False
