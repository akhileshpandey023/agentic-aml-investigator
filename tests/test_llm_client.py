"""GIVEN. Covers only the parts of Phase 5 that don't require a live API
call or a local server — get_llm_client() is already-implemented routing
logic, so this mostly checks you haven't broken it, plus the one piece of
validation AnthropicLLMClient must do without needing network access.
"""

import pytest

from aml_agents import config, llm_client


def test_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "carrier-pigeon")
    with pytest.raises(ValueError, match="Unknown LLM_BACKEND"):
        llm_client.get_llm_client()


def test_anthropic_client_rejects_empty_api_key():
    with pytest.raises(ValueError):
        llm_client.AnthropicLLMClient(api_key="", model="claude-sonnet-4-6")


def test_local_client_rejects_empty_model():
    with pytest.raises(ValueError):
        llm_client.LocalOpenAICompatLLMClient(base_url="http://localhost:11434/v1", model="")
