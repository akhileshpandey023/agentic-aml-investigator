"""The durable case record — separate from LangGraph's checkpointer.

PLACEHOLDER — see PROJECT_PLAN.md Phase 10, section "case_store.py".

_SCHEMA below is GIVEN (it's a data contract, like the Pydantic models in
schemas.py) — implement the functions that read/write against it.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aml_agents import config
from aml_agents.schemas import CaseState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    entity_name TEXT NOT NULL,
    original_query TEXT,
    risk_score INTEGER,
    risk_level TEXT,
    recommended_action TEXT,
    human_review_required INTEGER NOT NULL DEFAULT 0,
    human_decision TEXT,
    revision_count INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def _connect(db_path: Path = config.CASE_STORE_DB_PATH) -> Iterator[sqlite3.Connection]:
    # TODO (PROJECT_PLAN.md Phase 10): ensure db_path.parent exists, open a
    # sqlite3 connection with row_factory = sqlite3.Row, yield it, commit on
    # the way out (even on exception, via try/finally), and always close it.
    raise NotImplementedError("_connect: see PROJECT_PLAN.md Phase 10")


def init_db(db_path: Path = config.CASE_STORE_DB_PATH) -> None:
    # TODO: open a connection via _connect and execute _SCHEMA.
    raise NotImplementedError("init_db: see PROJECT_PLAN.md Phase 10")


def _state_to_json(state: CaseState) -> str:
    """TODO: json.dumps(dict(state), default=...) with a `default` function
    that calls .model_dump() on any Pydantic model it encounters (CaseState
    holds EntityMatch/RiskMemo/etc. instances, which json.dumps can't
    serialise on its own).
    """

    raise NotImplementedError("_state_to_json: see PROJECT_PLAN.md Phase 10")


def save_case(state: CaseState, db_path: Path = config.CASE_STORE_DB_PATH) -> None:
    """TODO (PROJECT_PLAN.md Phase 10): upsert one row into `cases` keyed on
    case_id, pulling risk_score/risk_level/recommended_action out of
    state["risk_memo"] (all None if no memo yet), human_decision out of
    state["human_decision"], and the full state via _state_to_json. Call
    init_db first so this works on a fresh database.
    """

    raise NotImplementedError("save_case: see PROJECT_PLAN.md Phase 10")


def get_case(case_id: str, db_path: Path = config.CASE_STORE_DB_PATH) -> dict | None:
    # TODO: SELECT * FROM cases WHERE case_id = ?, return a dict or None.
    raise NotImplementedError("get_case: see PROJECT_PLAN.md Phase 10")


def list_cases(
    *,
    pending_human_review: bool | None = None,
    db_path: Path = config.CASE_STORE_DB_PATH,
) -> list[dict]:
    """TODO: list cases, newest-updated first. When pending_human_review is
    True, filter to human_review_required = 1 AND human_decision IS NULL.
    """

    raise NotImplementedError("list_cases: see PROJECT_PLAN.md Phase 10")
