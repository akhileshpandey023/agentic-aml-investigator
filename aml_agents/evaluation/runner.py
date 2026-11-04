"""Run the system on golden cases and score it with deepeval.

Three levels, cheapest first. Each is one evaluation run:

    entity  entity_resolution_node only. No LLM, no graph, seconds. Tests the
            fuzzy-match threshold. Deterministic metrics only.
    e2e     the full compiled graph on every golden case. Needs the LLM (and
            the retrieval corpus). Deterministic metrics, plus the LLM-judged
            ones when a judge is supplied.
    critic  the Critic node on seeded good/defective memos (critic_cases.py).
            Needs the LLM. Measures catch rate and false-positive rate.

Isolation: nothing here writes to the case store or the LangGraph checkpoint
database. The e2e level uses an in-memory checkpointer and a unique thread_id
per case, and stops at the human gate without resuming (the paused state
already holds the memo and the escalation flag, which is what is scored).
Only the eval database persists.
"""

from __future__ import annotations

import contextlib
import io
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig
from deepeval.metrics import BaseMetric

from aml_agents.evaluation import deepeval_metrics as dm
from aml_agents.evaluation.adapters import CaseRun, to_test_case
from aml_agents.evaluation.critic_cases import build_critic_cases
from aml_agents.evaluation.test_cases import GoldenCase, all_cases
from aml_agents.schemas import CaseState, new_case_state

# --------------------------------------------------------------------------
# Running the system
# --------------------------------------------------------------------------


def _merge(state: CaseState, update: dict) -> None:
    """Apply a node's return value the way LangGraph would: overwrite every
    key except `trace`, which appends."""

    for key, value in update.items():
        if key == "trace":
            state["trace"] = list(state.get("trace", [])) + list(value)
        else:
            state[key] = value  # type: ignore[literal-required]


def run_entity_level(cases: Iterable[GoldenCase] | None = None) -> list[CaseRun]:
    from aml_agents.nodes.entity_resolution import entity_resolution_node

    runs = []
    for index, case in enumerate(cases if cases is not None else all_cases()):
        state = new_case_state(case["entity_name"])
        error = None
        try:
            _merge(state, entity_resolution_node(state))
        except Exception as exc:  # a failing case is a result, not a reason to stop the run
            error = f"{type(exc).__name__}: {exc}"
        runs.append(CaseRun(index=index, case=case, state=state, error=error))
    return runs


def run_graph_level(
    cases: Iterable[GoldenCase] | None = None,
    build: Callable[..., Any] | None = None,
) -> list[CaseRun]:
    """Run the full graph per case. `build` is injectable for tests."""

    from langgraph.checkpoint.memory import MemorySaver

    if build is None:
        from aml_agents.graph import build_graph as build

    app = build(checkpointer=MemorySaver())
    tag = uuid.uuid4().hex[:8]
    runs = []
    for index, case in enumerate(cases if cases is not None else all_cases()):
        run_config = {"configurable": {"thread_id": f"eval-{tag}-{index}"}}
        error, paused, state = None, False, None
        try:
            app.invoke(new_case_state(case["entity_name"]), run_config)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        snapshot = app.get_state(run_config)  # last checkpoint, also after a mid-run failure
        state = dict(snapshot.values) if snapshot.values else None
        paused = bool(snapshot.next) and error is None
        runs.append(CaseRun(index=index, case=case, state=state, error=error, paused=paused))  # type: ignore[arg-type]
    return runs


def run_critic_level() -> list[CaseRun]:
    from aml_agents.nodes.critic import critic_node

    runs = []
    for index, critic_case in enumerate(build_critic_cases()):
        state = critic_case["state"]
        label = {k: critic_case[k] for k in ("entity_name", "category", "expected_verdict", "defect")}  # type: ignore[literal-required]
        error = None
        try:
            _merge(state, critic_node(state))
        except Exception as exc:  # e.g. unparseable critic JSON: scored as a miss
            error = f"{type(exc).__name__}: {exc}"
        runs.append(CaseRun(index=index, case=label, state=state, error=error))
    return runs


# --------------------------------------------------------------------------
# Scoring with deepeval
# --------------------------------------------------------------------------


def _evaluate(runs: list[CaseRun], metrics: list[BaseMetric]) -> list[dict]:
    """One deepeval evaluate() call; returns a score row per (case, metric).

    - Caching is off: a cached result would hide the effect of a changed
      threshold or prompt, which is the thing being measured.
    - ignore_errors keeps one failed judge call from aborting the batch; the
      error is recorded on the row.
    - Metrics run synchronously (async_mode=False on each) so a local model
      is not hit with parallel requests.
    """

    if not runs or not metrics:
        return []
    # deepeval prints a results banner (and a Confident AI promo) from inside
    # evaluate() regardless of DisplayConfig; this harness has its own summary.
    with contextlib.redirect_stdout(io.StringIO()):
        result = evaluate(
            test_cases=[to_test_case(r) for r in runs],
            metrics=metrics,
            async_config=AsyncConfig(run_async=False),
            display_config=DisplayConfig(print_results=False, show_indicator=False, verbose_mode=False),
            cache_config=CacheConfig(write_cache=False, use_cache=False),
            error_config=ErrorConfig(ignore_errors=True),
        )
    rows = []
    for test_result in result.test_results:
        case_index = int(str(test_result.name).rsplit("-", 1)[-1])
        for data in test_result.metrics_data or []:
            rows.append(
                {
                    "case_index": case_index,
                    "metric_name": data.name,
                    "score": data.score,
                    "passed": data.success,
                    "reason": data.reason,
                    "error": data.error,
                }
            )
    return rows


def score_runs(runs: list[CaseRun], level: str, judge: Any | None = None) -> list[dict]:
    """Score `runs` for `level`. LLM-judged metrics run only when a judge is
    given and only on cases that produced a memo."""

    if level == "entity":
        return _evaluate(runs, [m() for m in dm.ENTITY_METRICS])
    if level == "critic":
        return _evaluate(runs, [m() for m in dm.CRITIC_METRICS])
    if level == "e2e":
        rows = _evaluate(runs, [m() for m in dm.E2E_DETERMINISTIC_METRICS])
        if judge is not None:
            with_memo = [r for r in runs if r.state and r.state.get("risk_memo") is not None]
            rows += _evaluate(with_memo, dm.build_llm_metrics(judge))
        return rows
    raise ValueError(f"Unknown level: {level!r} (expected entity, e2e or critic)")


def run_level(level: str, judge: Any | None = None, cases: Iterable[GoldenCase] | None = None) -> list[CaseRun]:
    if level == "entity":
        return run_entity_level(cases)
    if level == "e2e":
        return run_graph_level(cases)
    if level == "critic":
        return run_critic_level()
    raise ValueError(f"Unknown level: {level!r} (expected entity, e2e or critic)")
