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
    "* **Streamlit Cloud** — under *App settings → Secrets*, paste exactly:\n"
    '  `ANTHROPIC_API_KEY = "sk-ant-..."` (TOML: the value MUST be quoted, and the '
    "key must be top-level, not under a `[section]`).\n"
    "* **Locally** — add `ANTHROPIC_API_KEY=sk-ant-...` to a `.env` file in the repo "
    "root (a plain `.env`, so no quotes needed there)."
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


def diagnose_secrets() -> str:
    """Why st.secrets did not yield a key — WITHOUT ever revealing a value.

    The broad `except` above is right (a missing secrets file must not crash the
    page) but it is indiscriminate: a TOML parse error, a misspelled key and a
    nested `[section]` all collapse into the same silent None, and the user is
    told "no key" when the truth is "your key is there but I could not read it".
    On Streamlit Cloud, where you cannot open a shell and print things, that
    ambiguity is the whole debugging difficulty.

    So this reports what was SEEN: the exception class, or the top-level key NAMES
    present. Names only. A value is never returned, never logged, never rendered —
    the point is to debug the wiring, not to print the credential into a browser.
    """
    try:
        import streamlit as st
    except Exception as error:  # noqa: BLE001
        return f"streamlit could not be imported ({type(error).__name__})."

    try:
        names = list(st.secrets.keys())
    except Exception as error:  # noqa: BLE001
        # Reached when there is no secrets file at all (normal locally), and ALSO
        # when the TOML is malformed — e.g. an unquoted value, which is the single
        # most common way this goes wrong on Cloud.
        return (
            f"st.secrets could not be read ({type(error).__name__}). Either no "
            "secrets are configured, or the TOML is malformed — an unquoted value "
            "is a parse error."
        )

    if not names:
        return "st.secrets is readable but EMPTY — no secrets are configured."

    if SECRET_NAME in names:
        # The name is present, so the value must be empty or whitespace.
        return (
            f"st.secrets contains {SECRET_NAME}, but its value is empty after "
            "stripping."
        )

    return (
        f"st.secrets is readable and contains {len(names)} top-level key(s): "
        f"{', '.join(sorted(names))} — but NOT {SECRET_NAME}. It must be top-level, "
        "not nested under a [section]."
    )


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
