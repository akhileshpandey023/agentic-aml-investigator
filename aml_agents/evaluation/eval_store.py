"""SQLite store for evaluation output. PLACEHOLDER — see PROJECT_PLAN.md
Phase 11, section "eval_store.py" for the schema and function requirements.

All eval results live in SQLite at config.EVAL_DB_PATH; no CSV or JSON
result files. Follow the same _connect pattern as memory/case_store.py.
"""

from __future__ import annotations

from pathlib import Path

from aml_agents import config
from aml_agents.evaluation.test_cases import GoldenCase
from aml_agents.schemas import CaseState


def init_eval_db(db_path: Path = config.EVAL_DB_PATH) -> None:
    """TODO: create eval_runs, eval_results and eval_metrics. See PROJECT_PLAN.md Phase 11."""

    raise NotImplementedError("init_eval_db: see PROJECT_PLAN.md Phase 11")


def start_run(*, notes: str = "", db_path: Path = config.EVAL_DB_PATH) -> str:
    """TODO: insert an eval_runs row (with a config snapshot) and return its run_id."""

    raise NotImplementedError("start_run: see PROJECT_PLAN.md Phase 11")


def save_results(
    run_id: str,
    cases: list[GoldenCase],
    results: list[CaseState],
    db_path: Path = config.EVAL_DB_PATH,
) -> None:
    """TODO: write one eval_results row per (case, result) pair."""

    raise NotImplementedError("save_results: see PROJECT_PLAN.md Phase 11")


def save_metric(
    run_id: str,
    name: str,
    value: float,
    details: dict | None = None,
    db_path: Path = config.EVAL_DB_PATH,
) -> None:
    """TODO: upsert one eval_metrics row."""

    raise NotImplementedError("save_metric: see PROJECT_PLAN.md Phase 11")


def compare_runs(run_a: str, run_b: str, db_path: Path = config.EVAL_DB_PATH) -> list[dict]:
    """TODO: one row per metric with both runs' values and the difference."""

    raise NotImplementedError("compare_runs: see PROJECT_PLAN.md Phase 11")
