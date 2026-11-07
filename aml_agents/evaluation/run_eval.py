"""Evaluation CLI.

    uv run python -m aml_agents.evaluation.run_eval run --level entity
    uv run python -m aml_agents.evaluation.run_eval run --level e2e --judge --notes "baseline"
    uv run python -m aml_agents.evaluation.run_eval run --level critic
    uv run python -m aml_agents.evaluation.run_eval list
    uv run python -m aml_agents.evaluation.run_eval compare <run_a> <run_b>

See EVAL_PLAN.md for what each level measures and how to read the output.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from aml_agents import config
from aml_agents.evaluation import eval_store, metrics
from aml_agents.evaluation.adapters import CaseRun
from aml_agents.evaluation.runner import run_level, score_runs
from aml_agents.schemas import new_case_state

LEVELS = ("entity", "e2e", "critic")


def _states(runs: list[CaseRun]):
    return [r.state or new_case_state(r.case["entity_name"]) for r in runs]


def aggregate(level: str, runs: list[CaseRun], rows: list[dict]) -> dict[str, tuple[float, dict | None]]:
    """Run-level metrics as {name: (value, details)}."""

    out: dict[str, tuple[float, dict | None]] = {}
    errored = [r for r in runs if r.error]
    out[f"{level}.errors"] = (
        float(len(errored)),
        {"n_cases": len(runs), "first_error": errored[0].error} if errored else None,
    )
    states = _states(runs)

    if level in ("entity", "e2e"):
        cases = [dict(r.case) for r in runs]
        acc = metrics.entity_resolution_accuracy(cases, states)  # type: ignore[arg-type]
        for key in ("accuracy", "precision", "recall"):
            out[f"entity_resolution.{key}"] = (acc[key], {k: acc[k] for k in ("tp", "fp", "tn", "fn")})
    if level == "e2e":
        out["e2e.pause_rate"] = (sum(r.paused for r in runs) / len(runs) if runs else float("nan"), None)
        for node, stats in metrics.latency_by_node(states).items():
            out[f"latency.{node}.mean_ms"] = (stats["mean_ms"], stats)
    if level == "critic":
        rates = metrics.critic_rates(rows, [dict(r.case) for r in runs])
        out["critic.catch_rate"] = (rates["catch_rate"], rates)
        out["critic.false_positive_rate"] = (rates["false_positive_rate"], rates)

    for name, s in metrics.summarise_scores(rows).items():
        out[f"deepeval.{name}.mean"] = (s["mean"], s)
        out[f"deepeval.{name}.pass_rate"] = (s["pass_rate"], s)
        out[f"deepeval.{name}.errors"] = (float(s["errors"]), None)
    return out


def execute(
    level: str,
    *,
    judge: Any | None = None,
    notes: str = "",
    cases: list | None = None,
    db_path: Path = config.EVAL_DB_PATH,
) -> str:
    """Run one level, score it, store everything, return the run_id.
    `cases` overrides the golden set (entity and e2e levels)."""

    runs = run_level(level, cases=cases)
    rows = score_runs(runs, level, judge)
    run_id = eval_store.start_run(
        notes=f"[{level}] {notes}".strip(),
        extra_config={"level": level, "judge": judge.get_model_name() if judge else None, "n_cases": len(runs)},
        db_path=db_path,
    )
    eval_store.save_results(run_id, [dict(r.case) for r in runs], _states(runs), db_path)  # type: ignore[arg-type]
    eval_store.save_case_scores(run_id, rows, db_path)
    for name, (value, details) in aggregate(level, runs, rows).items():
        eval_store.save_metric(run_id, name, value, details, db_path)
    return run_id


def _fmt(value: float | None) -> str:
    return "n/a" if value is None or math.isnan(value) else f"{value:.3f}"


def print_run(run_id: str, db_path: Path = config.EVAL_DB_PATH) -> None:
    print(f"\nrun {run_id}")
    for name, value in eval_store.get_metrics(run_id, db_path).items():
        print(f"  {name:<52} {_fmt(value)}")
    for name, details in eval_store.get_metric_details(run_id, db_path).items():
        if name.endswith(".errors") and details and details.get("first_error"):
            print(
                f"\n  WARNING: {int(eval_store.get_metrics(run_id, db_path)[name])} of {details['n_cases']} cases "
                f"failed to run, so the metrics above are not meaningful.\n  First error: {details['first_error']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run an evaluation level and store the results")
    p_run.add_argument("--level", choices=[*LEVELS, "all"], required=True)
    p_run.add_argument("--judge", action="store_true", help="also run LLM-judged metrics (e2e level)")
    p_run.add_argument("--notes", default="")

    sub.add_parser("list", help="List stored runs")
    p_cmp = sub.add_parser("compare", help="Compare two runs metric by metric")
    p_cmp.add_argument("run_a")
    p_cmp.add_argument("run_b")
    args = parser.parse_args()

    if args.command == "run":
        judge = None
        if args.judge:
            from aml_agents.evaluation.judge import get_judge

            judge = get_judge()
        for level in LEVELS if args.level == "all" else (args.level,):
            run_id = execute(level, judge=judge if level == "e2e" else None, notes=args.notes)
            print_run(run_id)
    elif args.command == "list":
        for r in eval_store.list_runs():
            print(f"{r['run_id']}  {r['started_at']}  {r['llm_backend']}:{r['llm_model']}  {r['notes']}")
    elif args.command == "compare":
        print(f"{'metric':<52} {'A':>8} {'B':>8} {'B-A':>8}")
        for r in eval_store.compare_runs(args.run_a, args.run_b):
            print(f"{r['metric_name']:<52} {_fmt(r['value_a']):>8} {_fmt(r['value_b']):>8} {_fmt(r['diff']):>8}")


if __name__ == "__main__":
    main()
