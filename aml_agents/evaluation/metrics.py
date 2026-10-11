"""Metrics for the Phase 11 evaluation harness. PLACEHOLDER — see
PROJECT_PLAN.md Phase 11 for detailed requirements for each function.
"""

from __future__ import annotations

from aml_agents.evaluation.test_cases import GoldenCase
from aml_agents.schemas import CaseState


def entity_resolution_accuracy(cases: list[GoldenCase], results: list[CaseState]) -> dict:
    """TODO: compare CaseState["entity_resolved"] against each golden case's
    expected_entity_resolved; return tp/fp/tn/fn counts plus accuracy,
    precision, recall. See PROJECT_PLAN.md Phase 11.
    """

    raise NotImplementedError("entity_resolution_accuracy: see PROJECT_PLAN.md Phase 11")


def latency_by_node(results: list[CaseState]) -> dict[str, dict]:
    """TODO: aggregate AgentTrace.duration_ms per node_name across a batch of
    runs (count, mean_ms, max_ms per node). See PROJECT_PLAN.md Phase 11.
    """

    raise NotImplementedError("latency_by_node: see PROJECT_PLAN.md Phase 11")


def critic_catch_rate(_broken_memos_with_known_issues, _critic_reviews) -> float:
    """TODO (stretch): fraction of deliberately-broken memos the critic
    correctly flags as "revise". See PROJECT_PLAN.md Phase 11.
    """

    raise NotImplementedError("critic_catch_rate needs a hand-built set of deliberately-broken memos")


def retrieval_faithfulness(_cases, _results) -> dict:
    """TODO (stretch): reuse your existing RAGAS-style faithfulness setup
    from the compliance Q&A assistant, adapted to this project's schemas.
    """

    raise NotImplementedError("reuse your existing RAGAS evaluation setup, adapted to this project's schemas")
