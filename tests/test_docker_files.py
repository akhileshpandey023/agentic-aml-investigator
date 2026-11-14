"""Cheap static checks on the deployment files (no Docker needed)."""

import re
from pathlib import Path

from aml_agents import config

ROOT = Path(__file__).resolve().parent.parent


def test_warm_script_model_matches_config():
    text = (ROOT / "scripts" / "warm_models.py").read_text()
    assert config.CROSS_ENCODER_MODEL in text


def test_dockerignore_keeps_secrets_and_data_out_of_image():
    lines = (ROOT / ".dockerignore").read_text().split()
    for must in (".env", "data", ".venv", ".git"):
        assert must in lines


def test_dockerfile_basics():
    text = (ROOT / "Dockerfile").read_text()
    assert re.search(r"^USER appuser", text, re.M)
    assert "--host\", \"0.0.0.0\"" in text and "\"--workers\", \"1\"" in text
    assert text.index("COPY pyproject.toml uv.lock") < text.index("COPY aml_agents")
    assert "ANTHROPIC_API_KEY" not in text


def test_lockfile_includes_api_dependencies():
    lock = (ROOT / "uv.lock").read_text()
    assert 'name = "fastapi"' in lock and 'name = "uvicorn"' in lock
