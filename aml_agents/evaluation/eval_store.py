"""SQLite store for evaluation output (Phase 11).

All eval results live in SQLite at config.EVAL_DB_PATH; no CSV or JSON result
files. deepeval computes the scores; this module is the system of record, so
two runs can be compared after a config or prompt change (compare_runs).

Tables
    eval_runs          one row per run: backend/model, config snapshot, notes
    eval_results       one row per evaluated case: labels, outcome, full state
    eval_case_scores   one row per (case, deepeval metric): score, pass, reason
    eval_metrics       run-level aggregates (accuracy, pass rates, latency)
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aml_agents import config
from aml_agents.evaluation.test_cases import GoldenCase
from aml_agents.memory.case_store import _state_to_json
from aml_agents.schemas import CaseState

_SCHEMA = [
    """
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
    CREATE TABLE IF NOT EXISTS eval_case_scores (
        run_id TEXT,
        case_index INTEGER,
        metric_name TEXT,
        score REAL,
        passed INTEGER,
        reason TEXT,
        error TEXT,
        PRIMARY KEY (run_id, case_index, metric_name)
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
    """,
]

_CONFIG_KEYS = (
    "ENTITY_MATCH_MIN_SCORE", "ENTITY_MATCH_TOP_K", "RETRIEVAL_TOP_K", "RETRIEVAL_RERANK_TOP_K",
    "ADVERSE_MEDIA_RELEVANCE_SCORE", "MAX_REVISIONS", "RISK_ESCALATION_THRESHOLD",
    "CRITIC_MIN_CONFIDENCE", "EVAL_JUDGE_BACKEND", "EVAL_JUDGE_MODEL",
)


@contextmanager
def _connect(db_path: Path = config.EVAL_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_eval_db(db_path: Path = config.EVAL_DB_PATH) -> None:
    with _connect(db_path) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)


def config_snapshot(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Thresholds that can move a metric, captured so a change in results can
    be traced to a change in config."""

    snapshot = {key: getattr(config, key) for key in _CONFIG_KEYS}
    snapshot.update(extra or {})
    return snapshot


def start_run(
    *,
    notes: str = "",
    extra_config: dict[str, Any] | None = None,
    db_path: Path = config.EVAL_DB_PATH,
) -> str:
    """Insert an eval_runs row (with a config snapshot) and return its run_id."""

    init_eval_db(db_path)
    run_id = uuid.uuid4().hex[:12]
    model = config.ANTHROPIC_MODEL if config.LLM_BACKEND == "anthropic" else config.LOCAL_LLM_MODEL
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO eval_runs (run_id, started_at, llm_backend, llm_model, config_json, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                datetime.now(UTC).isoformat(timespec="seconds"),
                config.LLM_BACKEND,
                model,
                json.dumps(config_snapshot(extra_config), default=str),
                notes,
            ),
        )
    return run_id


def save_results(
    run_id: str,
    cases: list[GoldenCase],
    results: list[CaseState],
    db_path: Path = config.EVAL_DB_PATH,
) -> None:
    """One eval_results row per (case, result) pair. `cases` and `results` are
    parallel lists; case_index is the position."""

    if len(cases) != len(results):
        raise ValueError("cases and results must have the same length")
    init_eval_db(db_path)
    with _connect(db_path) as conn:
        for index, (case, state) in enumerate(zip(cases, results, strict=True)):
            durations = [t.duration_ms for t in state.get("trace", []) if t.duration_ms is not None]
            expected = case.get("expected_entity_resolved")
            resolved = state.get("entity_resolved")
            conn.execute(
                "INSERT OR REPLACE INTO eval_results (run_id, case_index, entity_name, category, "
                "expected_entity_resolved, entity_resolved, duration_ms, state_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, index, case["entity_name"], case.get("category"),
                    None if expected is None else int(expected),
                    None if resolved is None else int(resolved),
                    sum(durations) if durations else None,
                    _state_to_json(state),
                ),
            )


def save_case_scores(run_id: str, rows: list[dict[str, Any]], db_path: Path = config.EVAL_DB_PATH) -> None:
    """Per-(case, metric) deepeval scores. Each row: case_index, metric_name,
    score, passed, reason, error."""

    init_eval_db(db_path)
    with _connect(db_path) as conn:
        for r in rows:
            conn.execute(
                "INSERT OR REPLACE INTO eval_case_scores (run_id, case_index, metric_name, score, passed, "
                "reason, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, r["case_index"], r["metric_name"], r.get("score"),
                    None if r.get("passed") is None else int(r["passed"]),
                    r.get("reason"), r.get("error"),
                ),
            )


def save_metric(
    run_id: str,
    name: str,
    value: float,
    details: dict | None = None,
    db_path: Path = config.EVAL_DB_PATH,
) -> None:
    """Upsert one eval_metrics row. NaN is stored as NULL."""

    init_eval_db(db_path)
    stored = None if math.isnan(value) else float(value)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eval_metrics (run_id, metric_name, metric_value, details_json) "
            "VALUES (?, ?, ?, ?)",
            (run_id, name, stored, json.dumps(details, default=str) if details else None),
        )


def get_metrics(run_id: str, db_path: Path = config.EVAL_DB_PATH) -> dict[str, float | None]:
    init_eval_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT metric_name, metric_value FROM eval_metrics WHERE run_id = ? ORDER BY metric_name", (run_id,)
        ).fetchall()
    return {r["metric_name"]: r["metric_value"] for r in rows}


def get_metric_details(run_id: str, db_path: Path = config.EVAL_DB_PATH) -> dict[str, dict]:
    init_eval_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT metric_name, details_json FROM eval_metrics WHERE run_id = ? AND details_json IS NOT NULL",
            (run_id,),
        ).fetchall()
    return {r["metric_name"]: json.loads(r["details_json"]) for r in rows}


def list_runs(db_path: Path = config.EVAL_DB_PATH) -> list[dict]:
    init_eval_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM eval_runs ORDER BY started_at DESC").fetchall()
    return [dict(r) for r in rows]


def compare_runs(run_a: str, run_b: str, db_path: Path = config.EVAL_DB_PATH) -> list[dict]:
    """One row per metric present in either run, with both values and
    diff = value_b - value_a (None when either side is missing or NULL)."""

    init_eval_db(db_path)
    sql = """
        WITH names AS (
            SELECT metric_name FROM eval_metrics WHERE run_id IN (?, ?) GROUP BY metric_name
        )
        SELECT n.metric_name AS metric_name,
               a.metric_value AS value_a,
               b.metric_value AS value_b,
               b.metric_value - a.metric_value AS diff
        FROM names n
        LEFT JOIN eval_metrics a ON a.run_id = ? AND a.metric_name = n.metric_name
        LEFT JOIN eval_metrics b ON b.run_id = ? AND b.metric_name = n.metric_name
        ORDER BY n.metric_name
    """
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, (run_a, run_b, run_a, run_b)).fetchall()]
