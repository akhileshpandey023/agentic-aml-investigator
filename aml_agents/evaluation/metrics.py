"""Aggregate metrics for the Phase 11 evaluation harness.

Pure functions, no LLM and no deepeval import. Per-case scoring (including the
LLM-judged faithfulness and critic checks that used to be stubs here) is done
by deepeval in deepeval_metrics.py / runner.py; this module rolls those scores
and the classic confusion-matrix numbers up to run-level metrics.
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


# --------------------------------------------------------------------------
# Aggregation of deepeval per-case scores (see runner.py)
#
# Score rows come from deepeval via runner.score_runs(): one dict per
# (case, metric) with case_index, metric_name, score, passed, reason, error.
# --------------------------------------------------------------------------


def summarise_scores(rows: list[dict]) -> dict[str, dict]:
    """Per metric: mean score, pass rate, and how many evaluations errored.
    Errored evaluations (judge failure, bad JSON) are excluded from the mean
    and pass rate and counted separately, so a flaky judge cannot masquerade
    as a score of zero."""

    by_metric: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_metric[row["metric_name"]].append(row)

    summary: dict[str, dict] = {}
    for name, items in by_metric.items():
        scored = [r for r in items if not r.get("error") and r.get("score") is not None]
        summary[name] = {
            "n": len(items),
            "errors": len(items) - len(scored),
            "mean": sum(r["score"] for r in scored) / len(scored) if scored else float("nan"),
            "pass_rate": sum(1 for r in scored if r["passed"]) / len(scored) if scored else float("nan"),
        }
    return summary


def critic_rates(rows: list[dict], cases: list[dict]) -> dict:
    """Catch rate and false-positive rate from "Critic Verdict Match" rows.
    `cases` is parallel to case_index. A critic run that errored (for example
    unparseable JSON) counts as a miss on defective memos and is excluded from
    the false-positive denominator."""

    verdict_rows = {r["case_index"]: r for r in rows if r["metric_name"] == "Critic Verdict Match"}
    caught = missed = false_pos = clean_ok = 0
    for index, case in enumerate(cases):
        row = verdict_rows.get(index)
        passed = bool(row and row["passed"] and not row.get("error"))
        if case["expected_verdict"] == "revise":
            caught, missed = (caught + 1, missed) if passed else (caught, missed + 1)
        elif row and not row.get("error"):
            clean_ok, false_pos = (clean_ok + 1, false_pos) if passed else (clean_ok, false_pos + 1)
    defective, clean = caught + missed, clean_ok + false_pos
    return {
        "catch_rate": caught / defective if defective else float("nan"),
        "false_positive_rate": false_pos / clean if clean else float("nan"),
        "defective_cases": defective,
        "clean_cases": clean,
    }
