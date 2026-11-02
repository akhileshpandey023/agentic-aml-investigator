"""Metrics for the Phase 11 evaluation harness. PLACEHOLDER — see
PROJECT_PLAN.md Phase 11 for detailed requirements for each function.
"""

from __future__ import annotations

from collections import defaultdict

from aml_agents.evaluation.test_cases import GoldenCase
from aml_agents.schemas import CaseState


def entity_resolution_accuracy(cases: list[GoldenCase], results: list[CaseState]) -> dict:
    """Compare entity-resolution outcomes against the golden-case labels."""
    if len(cases) != len(results):
        raise ValueError("cases and results must have the same length")

    true_positive = false_positive = true_negative = false_negative = 0

    for case, result in zip(cases, results, strict=True):
        expected = case["expected_entity_resolved"]
        actual = result["entity_resolved"]

        if expected and actual:
            true_positive += 1
        elif not expected and actual:
            false_positive += 1
        elif not expected and not actual:
            true_negative += 1
        else:
            false_negative += 1

    total = len(cases)
    return {
        "tp": true_positive,
        "fp": false_positive,
        "tn": true_negative,
        "fn": false_negative,
        "accuracy": (true_positive + true_negative) / total if total else float("nan"),
        "precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else float("nan"),
        "recall": true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else float("nan"),
    }


def latency_by_node(results: list[CaseState]) -> dict[str, dict]:
    """Aggregate non-null trace durations by graph-node name."""
    durations_by_node: dict[str, list[float]] = defaultdict(list)

    for result in results:
        for trace in result.get("trace", []):
            if trace.duration_ms is not None:
                durations_by_node[trace.node_name].append(trace.duration_ms)

    return {
        node_name: {
            "count": len(durations),
            "mean_ms": sum(durations) / len(durations),
            "max_ms": max(durations),
        }
        for node_name, durations in durations_by_node.items()
    }


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
