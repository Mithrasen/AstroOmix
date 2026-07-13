"""API key resolution that works locally AND on Streamlit Cloud.

The failure this exists to prevent
----------------------------------
`src/env.py` reads the Anthropic key from a git-ignored `.env` via `dotenv_values`.
That file **does not exist on Streamlit Cloud** — it is git-ignored, so it is never
deployed. An agent that only knows how to read `.env` would find no key in
production and fail there while working perfectly on the developer's machine.
That is exactly the class of environment-mismatch bug that made the Render deploys
so painful to debug.

Resolution order
----------------
1. `st.secrets["ANTHROPIC_API_KEY"]` — how the deployed Cloud app gets its key.
2. The existing `.env` path — local development, unchanged.
3. Nothing. The agent page shows a friendly message; the rest of the app is
   untouched. This is a normal state, not a crash.

**Never `os.environ`.** `env.py`'s rule stands: the key never comes from the
ambient environment, because that environment is shared with Claude Code's own
billing and auth. Reading it from there could silently bill the wrong account.
`src/settings.py` reads `os.environ` for ALLOW_REFRESH — that is a deployment
flag, not a credential, and the distinction is deliberate.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.env import ENV_PATH, load_env

SECRET_NAME = "ANTHROPIC_API_KEY"

NOT_CONFIGURED_MESSAGE = (
    "**Research Assistant requires an API key — not configured in this environment.**\n\n"
    "Everything else in AstroOmix works without it. To enable the assistant:\n\n"
    "* **Streamlit Cloud** — add `ANTHROPIC_API_KEY` under *App settings → Secrets*.\n"
    "* **Locally** — add `ANTHROPIC_API_KEY=sk-ant-...` to a `.env` file in the repo root."
)


@dataclass(frozen=True)
class KeyResolution:
    """Where the key came from — or why there isn't one."""

    key: str | None
    source: str  # "streamlit_secrets" | "dotenv" | "none"

    @property
    def configured(self) -> bool:
        return bool(self.key)


def _from_streamlit_secrets() -> str | None:
    """Read st.secrets, degrading gracefully when there is no secrets file.

    `st.secrets` RAISES if no secrets.toml exists anywhere — which is the normal
    case on a developer's machine. That exception must not propagate: it would
    take down the page for someone whose key is sitting in `.env` and perfectly
    valid. Hence the broad except.
    """
    try:
        import streamlit as st

        value = st.secrets[SECRET_NAME]
    except Exception:
        return None

    value = str(value).strip()
    return value or None


def _from_dotenv() -> str | None:
    """The existing local path. `load_env` raises FileNotFoundError with no .env."""
    try:
        value = load_env(ENV_PATH).get(SECRET_NAME, "")
    except (FileNotFoundError, OSError):
        return None
    value = value.strip()
    return value or None


def resolve_api_key() -> KeyResolution:
    """st.secrets → .env → None. Never os.environ. Never raises."""
    key = _from_streamlit_secrets()
    if key:
        return KeyResolution(key, "streamlit_secrets")

    key = _from_dotenv()
    if key:
        return KeyResolution(key, "dotenv")

    return KeyResolution(None, "none")
