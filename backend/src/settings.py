"""Deployment flags.

Separate from `env.py`, which exists for one narrow purpose (the Anthropic API
key, read only from a git-ignored `.env` and never from the ambient environment).
These are ordinary deployment flags and are safe to read from `os.environ` —
that rule is about the API key specifically, not about environment variables in
general.
"""

from __future__ import annotations

import os

from src.env import ENV_PATH, load_env


def _flag(name: str, default: str = "false") -> bool:
    """Read a boolean flag from the shell environment, falling back to `.env`.

    `env.py` deliberately never writes into `os.environ`, so a value set only in
    `.env` would otherwise be invisible here. Checking both means either local
    workflow works: `ALLOW_REFRESH=true uvicorn ...` or a line in `.env`.

    The shell wins, so a Render dashboard setting can never be overridden by a
    stray committed file.
    """
    value = os.environ.get(name)

    if value is None:
        try:
            value = load_env(ENV_PATH).get(name)
        except FileNotFoundError:
            value = None

    return (value if value is not None else default).strip().lower() == "true"


def allow_refresh() -> bool:
    """Whether cache-bypassing `?refresh=true` is permitted.

    Defaults CLOSED. This is a safety limit, not a preference.

    An uncached DESeq2 run peaks at ~2.4 GB of unique memory across ~18 worker
    processes. Render's free tier caps at 512 MB, so `?refresh=true` in
    production does not merely make a request slow — it gets the dyno
    OOM-killed, taking every other endpoint down with it. The committed cache in
    `data/cache/de/` is what keeps DESeq2 from ever running in production, and
    `refresh` is the one public parameter that can defeat it.

    Read at call time, not at import, so tests and a running process can change
    it without a restart.
    """
    return _flag("ALLOW_REFRESH")
