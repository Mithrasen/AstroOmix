import os

import pytest

from src.env import get_anthropic_api_key, load_env


def write_env(tmp_path, content):
    path = tmp_path / ".env"
    path.write_text(content)
    return path


def test_load_env_reads_pairs(tmp_path):
    path = write_env(tmp_path, "ANTHROPIC_API_KEY=sk-ant-abc\nREGION=us\n")
    assert load_env(path) == {"ANTHROPIC_API_KEY": "sk-ant-abc", "REGION": "us"}


def test_get_key_returns_value(tmp_path):
    path = write_env(tmp_path, "ANTHROPIC_API_KEY=sk-ant-abc\n")
    assert get_anthropic_api_key(path) == "sk-ant-abc"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_anthropic_api_key(tmp_path / "nope.env")


def test_empty_key_raises(tmp_path):
    path = write_env(tmp_path, "ANTHROPIC_API_KEY=\n")
    with pytest.raises(KeyError):
        get_anthropic_api_key(path)


def test_never_falls_back_to_ambient_environment(tmp_path, monkeypatch):
    """The ambient shell shares Claude Code's billing/auth. A key present in
    os.environ must not satisfy a .env that lacks one."""
    monkeypatch.setitem(os.environ, "ANTHROPIC_API_KEY", "sk-ant-ambient-must-not-leak")

    path = write_env(tmp_path, "REGION=us\n")
    with pytest.raises(KeyError):
        get_anthropic_api_key(path)

    path = write_env(tmp_path, "ANTHROPIC_API_KEY=sk-ant-from-file\n")
    assert get_anthropic_api_key(path) == "sk-ant-from-file"
