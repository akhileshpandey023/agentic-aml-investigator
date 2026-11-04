"""Adapter that lets deepeval metrics use this project's LLM clients as the judge.

deepeval's LLM-judged metrics (FaithfulnessMetric, GEval) need a model that
implements `DeepEvalBaseLLM`. This wraps any `LLMClient` from
`aml_agents.llm_client`, so the judge can be the Anthropic API or a local
OpenAI-compatible/Ollama model with no deepeval-specific setup.

Judge choice matters: scores from a small local model grading its own output
are noisy. Set EVAL_JUDGE_BACKEND (config.py / .env) to grade with a different,
stronger model than the one under test.
"""

from __future__ import annotations

import json
import re
from typing import Any

from deepeval.models import DeepEvalBaseLLM

from aml_agents import config
from aml_agents.llm_client import (
    AnthropicLLMClient,
    LLMClient,
    LocalOpenAICompatLLMClient,
    get_llm_client,
)

_JUDGE_SYSTEM = (
    "You are a careful evaluation judge. Follow the instructions in the user "
    "message exactly. When asked for JSON, reply with a single JSON object and "
    "nothing else: no preamble, no markdown fences, no commentary."
)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object in `text`, tolerating markdown fences and
    surrounding prose, which small local models add even when told not to.
    Raises ValueError if no JSON object can be parsed.
    """

    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in judge output: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])


class LLMClientJudge(DeepEvalBaseLLM):
    """deepeval judge backed by an `LLMClient`."""

    def __init__(self, client: LLMClient, name: str, max_tokens: int = config.EVAL_JUDGE_MAX_TOKENS):
        self._client = client
        self._max_tokens = max_tokens
        super().__init__(model=name)

    def load_model(self) -> LLMClient:
        return self._client

    def get_model_name(self) -> str:
        return self.name

    def generate(self, prompt: str, schema: Any = None) -> Any:
        response = self._client.complete(
            system=_JUDGE_SYSTEM, user=prompt, max_tokens=self._max_tokens, temperature=0.0
        )
        if schema is None:
            return response.text
        try:
            return schema.model_validate(extract_json(response.text))
        except (ValueError, TypeError):
            # Hand the raw text back; deepeval's own JSON repair gets a second
            # try, and a genuine failure is recorded on the metric as an error
            # (we run with ignore_errors=True) instead of aborting the batch.
            return response.text

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        # Metrics are run with async_mode=False; this exists to satisfy the ABC.
        return self.generate(prompt, schema)


def get_judge_client() -> tuple[LLMClient, str]:
    """Build the judge's LLM client from config. Returns (client, display name)."""

    backend = config.EVAL_JUDGE_BACKEND
    if backend == "same":
        backend = config.LLM_BACKEND
        if not config.EVAL_JUDGE_MODEL:
            model = config.ANTHROPIC_MODEL if backend == "anthropic" else config.LOCAL_LLM_MODEL
            return get_llm_client(), f"{backend}:{model}"
    if backend == "anthropic":
        model = config.EVAL_JUDGE_MODEL or config.ANTHROPIC_MODEL
        return AnthropicLLMClient(config.ANTHROPIC_API_KEY, model), f"anthropic:{model}"
    if backend == "local":
        model = config.EVAL_JUDGE_MODEL or config.LOCAL_LLM_MODEL
        return LocalOpenAICompatLLMClient(config.LOCAL_LLM_BASE_URL, model), f"local:{model}"
    raise ValueError(f"Unknown EVAL_JUDGE_BACKEND: {config.EVAL_JUDGE_BACKEND!r}")


def get_judge() -> LLMClientJudge:
    client, name = get_judge_client()
    return LLMClientJudge(client, name)
