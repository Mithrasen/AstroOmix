"""The 403 gate for cache-bypassing `?refresh=true`."""

from __future__ import annotations

from fastapi import HTTPException

from src.settings import allow_refresh


def enforce_refresh_allowed(refresh: bool) -> None:
    """Reject `refresh=true` unless ALLOW_REFRESH=true in the environment.

    Fails LOUDLY with a 403 rather than silently serving the cached response.
    Silently ignoring the flag would be miserable to debug: a developer editing
    an analysis would hit `?refresh=true`, get a stale cached table back, and
    have no signal at all that their change never ran.
    """
    if refresh and not allow_refresh():
        raise HTTPException(
            status_code=403,
            detail=(
                "refresh is disabled in this environment. Re-running the analysis "
                "uncached peaks at ~2.4 GB of memory, which exceeds this deployment's "
                "limit and would take the whole service down. Set ALLOW_REFRESH=true "
                "to enable it locally."
            ),
        )
