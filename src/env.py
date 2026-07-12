"""Secrets loading.

Hard rule for this project: the Anthropic API key is read ONLY from a
git-ignored `.env` file via `dotenv_values`. It is never read from
`os.environ` / `os.getenv`, because the ambient shell environment is shared
with Claude Code's own billing and auth. Nothing in this repo should import
`os.environ` to look up ANTHROPIC_API_KEY.
"""

from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_env(env_path: Path = ENV_PATH) -> dict:
    """Return key/value pairs from the .env file. Does not touch os.environ."""
    if not env_path.is_file():
        raise FileNotFoundError(
            f"No .env file at {env_path}. Create one containing ANTHROPIC_API_KEY=..."
        )
    return {k: v for k, v in dotenv_values(env_path).items() if v is not None}


def get_anthropic_api_key(env_path: Path = ENV_PATH) -> str:
    """Return ANTHROPIC_API_KEY from the .env file, or raise if absent.

    Must never fall back to the ambient environment.
    """
    key = load_env(env_path).get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise KeyError(f"ANTHROPIC_API_KEY is missing or empty in {env_path}")
    return key
