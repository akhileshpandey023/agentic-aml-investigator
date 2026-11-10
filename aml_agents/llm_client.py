"""The only module that should know which LLM backend is being used.

Backends: Anthropic SDK, and any OpenAI-compatible local endpoint.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
import requests

from aml_agents import config


@dataclass
class LLMResponse:
    """GIVEN. Normalised shape every backend must return from complete()."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(abc.ABC):
    """GIVEN. Minimal interface every backend implements."""

    @abc.abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResponse:
        """Single-turn completion. Implementations are responsible only for
        making the call and normalising the response into an LLMResponse —
        prompt content is the caller's (a node's) responsibility.
        """
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    """Anthropic Messages API backend."""

    def __init__(self, api_key: str, model: str):
        if not api_key or not api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        if not model or not model.strip():
            raise ValueError("ANTHROPIC_MODEL is not set. See .env.example.")
        import anthropic  # lazy: only needed for this backend

        self._client = anthropic.Anthropic(api_key=api_key, timeout=config.LLM_TIMEOUT_SECONDS)
        self._model = model.strip()

    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


class LocalOpenAICompatLLMClient(LLMClient):
    """Talks to an OpenAI-compatible /v1/chat/completions endpoint (Ollama,
    vLLM, ...). `base_url` may be given with or without the /v1 suffix:
    "http://localhost:11434", ".../" and ".../v1" all work."""

    def __init__(self, base_url: str, model: str):
        if not model or not model.strip():
            raise ValueError("No local model name configured (LOCAL_LLM_MODEL).")
        base = base_url.strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        self._base_url = base
        self._model = model.strip()

    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        url = f"{self._base_url}/chat/completions"
        try:
            response = requests.post(url, json=payload, timeout=config.LLM_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Failed to get a completion from local LLM endpoint {url}: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected response structure from local LLM: {data}") from exc

        usage = data.get("usage") or {}
        return LLMResponse(
            text=content or "",
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


def get_llm_client() -> LLMClient:
    """GIVEN. Factory — reads config.LLM_BACKEND and returns the matching
    client. Trivial routing logic, not part of the exercise; the backends
    it routes to are what you're implementing.
    """

    if config.LLM_BACKEND == "anthropic":
        return AnthropicLLMClient(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
    if config.LLM_BACKEND == "local":
        return LocalOpenAICompatLLMClient(config.LOCAL_LLM_BASE_URL, config.LOCAL_LLM_MODEL)
    raise ValueError(f"Unknown LLM_BACKEND: {config.LLM_BACKEND!r} (expected 'anthropic' or 'local')")
