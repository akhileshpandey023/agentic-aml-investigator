"""Critic agent — the reflection/evaluator half of the evaluator-generator loop.

PLACEHOLDER — see PROJECT_PLAN.md Phase 8, section "critic.py", for the full
requirements: what groundedness and consistency checks the prompt must
cover, and the parsing behaviour.

Reads:  state["risk_memo"], state["entity_candidates"], state["adverse_media_findings"],
        state["regulatory_context"]
Writes: state["critic_feedback"], state["trace"]

Note on revision_count ownership: this node only judges (approve/revise).
risk_analyst.py owns incrementing revision_count; graph.py's router only
reads it. See ARCHITECTURE.md design principle 3.
"""

from __future__ import annotations

from aml_agents.schemas import CaseState


def _format_review_context(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 8): render state["risk_memo"] (as JSON)
    alongside the same evidence risk_analyst saw, so the critic can check
    groundedness, not just internal consistency.
    """

    raise NotImplementedError("_format_review_context: see PROJECT_PLAN.md Phase 8")


def _parse_critic_review(raw_text: str) -> "CriticReview":  # noqa: F821
    """TODO: json.loads + CriticReview.model_validate."""

    raise NotImplementedError("_parse_critic_review: see PROJECT_PLAN.md Phase 8")


def critic_node(state: CaseState) -> dict:
    """TODO (PROJECT_PLAN.md Phase 8): format the review context, write a
    system prompt covering groundedness + consistency checks, call the LLM,
    parse the response, and return
    {"critic_feedback": ..., **make_trace(...)}.
    """

    raise NotImplementedError("critic_node: see PROJECT_PLAN.md Phase 8")
