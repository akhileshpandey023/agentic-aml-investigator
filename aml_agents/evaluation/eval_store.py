"""SQLite store for evaluation output. PLACEHOLDER — see PROJECT_PLAN.md
Phase 11, section "eval_store.py" for the schema and function requirements.

All eval results live in SQLite at config.EVAL_DB_PATH; no CSV or JSON
result files. Follow the same _connect pattern as memory/case_store.py.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager
from aml_agents import config

from aml_agents.evaluation.test_cases import GoldenCase
from aml_agents.schemas import CaseState

_SCHEMA = ["""
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id TEXT PRIMARY KEY, 
    started_at TEXT, 
    llm_backend TEXT,
    llm_model TEXT, 
    config_json TEXT, 
    notes TEXT
);
""", 
"""
CREATE TABLE IF NOT EXISTS eval_results (
    run_id TEXT, 
    case_index INTEGER, 
    entity_name TEXT, 
    category TEXT, 
    expected_entity_resolved INTEGER, 
    entity_resolved INTEGER, 
    duration_ms REAL, 
    state_json TEXT, 
    PRIMARY KEY (run_id, case_index)
);
""",
"""
CREATE TABLE IF NOT EXISTS eval_metrics (
    run_id TEXT, 
    metric_name TEXT, 
    metric_value REAL, 
    details_json TEXT, 
    PRIMARY KEY (run_id, metric_name)
);
"""]


@contextmanager
def _connect(db_path: Path = config.CASE_STORE_DB_PATH) -> Iterator[sqlite3.Connection]:
    # TODO (PROJECT_PLAN.md Phase 10): ensure db_path.parent exists, open a
    # sqlite3 connection with row_factory = sqlite3.Row, yield it, commit on
    # the way out (even on exception, via try/finally), and always close it.
    
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        raise e
    else:
        conn.commit()
    finally:
        conn.close()


def init_eval_db(db_path: Path = config.EVAL_DB_PATH) -> None:
    """TODO: create eval_runs, eval_results and eval_metrics. See PROJECT_PLAN.md Phase 11."""
    for query in _SCHEMA:
        with _connect(db_path) as conn:
            conn.execute(query)


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
