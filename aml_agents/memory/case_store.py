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



def init_db(db_path: Path = config.CASE_STORE_DB_PATH) -> None:
    # TODO: open a connection via _connect and execute _SCHEMA.
    conn = _connect(db_path)
    conn.execute(f"{_SCHEMA}") # type: ignore


def _state_to_json(state: CaseState) -> str:
    """TODO: json.dumps(dict(state), default=...) with a `default` function
    that calls .model_dump() on any Pydantic model it encounters (CaseState
    holds EntityMatch/RiskMemo/etc. instances, which json.dumps can't
    serialise on its own).
    """
    state_str = json.dumps(dict(state), default=CaseState.model_dump) # type: ignore

    return state_str


def save_case(state: CaseState, db_path: Path = config.CASE_STORE_DB_PATH) -> None:
    """TODO (PROJECT_PLAN.md Phase 10): upsert one row into `cases` keyed on
    case_id, pulling risk_score/risk_level/recommended_action out of
    state["risk_memo"] (all None if no memo yet), human_decision out of
    state["human_decision"], and the full state via _state_to_json. Call
    init_db first so this works on a fresh database.
    """

    init_db(db_path)
    memo = state.get("risk_memo")
    human_decision = state.get("human_decision")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO cases (case_id, entity_name, original_query, risk_score, risk_level,
                                recommended_action, human_review_required, human_decision,
                                revision_count, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(case_id) DO UPDATE SET
                risk_score=excluded.risk_score,
                risk_level=excluded.risk_level,
                recommended_action=excluded.recommended_action,
                human_review_required=excluded.human_review_required,
                human_decision=excluded.human_decision,
                revision_count=excluded.revision_count,
                state_json=excluded.state_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                state["case_id"],
                state["entity_name"],
                state.get("original_query"),
                memo.risk_score if memo else None,
                memo.risk_level if memo else None,
                memo.recommended_action if memo else None,
                int(state.get("human_review_required", False)),
                human_decision.decision if human_decision else None,
                state.get("revision_count", 0),
                _state_to_json(state),
            ),
        )


def get_case(case_id: str, db_path: Path = config.CASE_STORE_DB_PATH) -> dict | None:
    # TODO: SELECT * FROM cases WHERE case_id = ?, return a dict or None.
    
    init_db(db_path)
    with _connect(db_path) as conn:
        case_info = conn.execute(
            """
            SELECT * FORM cases
            WHERE case_id = ?
            """,
            (
                case_id,
            ),
        ).fetchone()
        
        return None if case_info is None else dict(case_info)



def list_cases(
    *,
    pending_human_review: bool | None = None,
    db_path: Path = config.CASE_STORE_DB_PATH,
) -> list[dict]:
    """TODO: list cases, newest-updated first. When pending_human_review is
    True, filter to human_review_required = 1 AND human_decision IS NULL.
    """
 
    init_db(db_path)
    with _connect(db_path) as conn:
        if pending_human_review:
            cursor = conn.execute(
                """
                SELECT * FORM cases
                WHERE human_revie_required = 1 AND
                human_descision IS NULL
                ORDER BY updated_at DESC
                """,
            )
            cases = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

            return [dict(zip(columns, row)) for row in cases]
        else:
            cursor = conn.execute(
                """
                SELECT * FORM cases
                ORDER BY updated_at DESC
                """,
            )
            cases = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

            return [dict(zip(columns, row)) for row in cases]
