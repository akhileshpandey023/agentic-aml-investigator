"""The only module that should know which LLM backend is being used.

PLACEHOLDER — see PROJECT_PLAN.md Phase 5 for detailed requirements.

The interface (LLMClient, LLMResponse) and the factory function are given —
they're the contract the rest of the codebase is written against. What's
missing is each backend's `complete()` method: the actual request/response
handling for the Anthropic SDK and for an OpenAI-compatible local endpoint.
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
    """PLACEHOLDER. See PROJECT_PLAN.md Phase 5, section "AnthropicLLMClient"."""

    def __init__(self, api_key: str, model: str):
        # TODO: validate api_key is non-empty (raise ValueError with a
        # helpful message pointing at .env.example if it's missing), lazily
        # import the `anthropic` package, construct an anthropic.Anthropic
        # client, and store it + model on self for complete() to use.
        raise NotImplementedError("AnthropicLLMClient.__init__: see PROJECT_PLAN.md Phase 5")

    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResponse:
        # TODO: call self._client.messages.create(...), extract the text
        # from the response's content blocks, and return an LLMResponse
        # (including input/output token counts from the response's usage).
        raise NotImplementedError("AnthropicLLMClient.complete: see PROJECT_PLAN.md Phase 5")


class LocalOpenAICompatLLMClient(LLMClient):
    """PLACEHOLDER. Talks to any OpenAI-compatible /v1/chat/completions
    endpoint — e.g. Ollama or vLLM serving a model on your own hardware.
    See PROJECT_PLAN.md Phase 5, section "LocalOpenAICompatLLMClient".
    """

    def __init__(self, base_url: str, model: str):
        if not model or not model.strip():
            raise ValueError("No model name entered.")
        
        # Store properties, stripping trailing slash from the base URL
        self._base_url = base_url.rstrip('/')
        self._model = model.strip()

    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> LLMResponse:
        # TODO: POST to f"{self._base_url}/chat/completions" with a
        # standard OpenAI-style chat payload, parse choices[0].message.content
        # and the usage block, and return an LLMResponse.
        payload = {
            'model': self._model, 
            'messages':[
                {'role': 'system', 'content': system,
                 'role': 'user', 'content': user}
            ], 
            'max_tokens': max_tokens, 
            'temperature': temperature, 
            "stream": False
        }
        url = f'{self._base_url}/api/chat'
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to connect to local LLM endpoint at {url}: {e}")

        # Parse text content
        try:
            content = data["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected response structure from local LLM: {data}") from e

        return LLMResponse(text=content,
                           input_tokens=data.get('prompt_eval_count', 0),
                           output_tokens=data.get('eval_count', 0)
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
