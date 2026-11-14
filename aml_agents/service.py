"""Use-case layer shared by the CLI (main.py) and the HTTP API (api.py).

Both are thin adapters over these functions, so they cannot drift apart. The
compiled graph is passed in (not built here), which lets tests supply a graph
wired to a fake LLM. Errors are exceptions with meaning; each adapter decides
how to present them (exit message in the CLI, status code in the API).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from aml_agents import config
from aml_agents.graph import escalation_reasons
from aml_agents.memory import case_store
from aml_agents.schemas import AgentTrace, HumanDecision, RiskMemo, new_case_state

log = logging.getLogger("aml_agents.service")


class CaseNotFound(Exception):
    """No case with this id."""


class CaseNotPending(Exception):
    """The case exists but is not waiting for a human decision."""


class CaseResult(BaseModel):
    """What callers get back for a case, from either a live run or the store."""

    case_id: str
    entity_name: str
    status: Literal["completed", "awaiting_review"]
    risk_memo: RiskMemo | None = None
    review_reasons: list[str] = []
    human_decision: HumanDecision | None = None
    trace: list[AgentTrace] = []


class CaseSummary(BaseModel):
    case_id: str
    entity_name: str
    risk_score: int | None = None
    risk_level: str | None = None
    recommended_action: str | None = None
    status: Literal["completed", "awaiting_review"]
    updated_at: str | None = None


def _run_config(case_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": case_id}}


def _result_from_snapshot(snapshot: Any) -> CaseResult:
    state = dict(snapshot.values)
    waiting = bool(snapshot.next)
    return CaseResult(
        case_id=state["case_id"],
        entity_name=state["entity_name"],
        status="awaiting_review" if waiting else "completed",
        risk_memo=state.get("risk_memo"),
        review_reasons=escalation_reasons(state) if waiting else [],
        human_decision=state.get("human_decision"),
        trace=state.get("trace", []),
    )


def start_investigation(
    graph: Any, entity_name: str, *, db_path: Path = config.CASE_STORE_DB_PATH
) -> CaseResult:
    """Run a new investigation to completion or to the human-review pause, and
    save the case. LLM or other failures propagate; nothing is saved then."""

    started = time.perf_counter()
    state = new_case_state(entity_name=entity_name)
    cfg = _run_config(state["case_id"])
    graph.invoke(state, config=cfg)
    snapshot = graph.get_state(cfg)
    case_store.save_case(dict(snapshot.values), db_path)
    result = _result_from_snapshot(snapshot)
    log.info(
        "investigation case_id=%s status=%s duration_s=%.1f",
        result.case_id, result.status, time.perf_counter() - started,
    )
    return result


def resume_investigation(
    graph: Any,
    case_id: str,
    decision: str,
    reviewer: str,
    notes: str = "",
    *,
    db_path: Path = config.CASE_STORE_DB_PATH,
) -> CaseResult:
    """Record a human decision on a paused case, run past human_gate, save."""

    cfg = _run_config(case_id)
    snapshot = graph.get_state(cfg)
    if not snapshot.values:
        raise CaseNotFound(case_id)
    if tuple(snapshot.next) != ("human_gate",):
        raise CaseNotPending(
            f"Case {case_id} is not waiting for human review "
            f"(next steps: {list(snapshot.next) or 'none, already finished'})."
        )
    graph.update_state(cfg, {"human_decision": HumanDecision(decision=decision, reviewer=reviewer, notes=notes)})
    graph.invoke(None, config=cfg)
    snapshot = graph.get_state(cfg)
    case_store.save_case(dict(snapshot.values), db_path)
    log.info("resumed case_id=%s decision=%s reviewer=%s", case_id, decision, reviewer)
    return _result_from_snapshot(snapshot)


def _row_status(row: dict) -> str:
    waiting = row["human_review_required"] and row["human_decision"] is None
    return "awaiting_review" if waiting else "completed"


def _review_reasons_from_trace(trace: list[AgentTrace]) -> list[str]:
    """The reasons are recorded by the mark_human_review_required node as
    "Human review required: a; b. Pausing before human_gate."."""

    for entry in reversed(trace):
        if entry.node_name == "mark_human_review_required":
            text = entry.summary_out.removeprefix("Human review required: ").split(". Pausing before")[0]
            return [r.strip() for r in text.split(";") if r.strip()]
    return []


def get_case(case_id: str, *, db_path: Path = config.CASE_STORE_DB_PATH) -> CaseResult:
    """Read a saved case from the case store."""

    row = case_store.get_case(case_id, db_path)
    if row is None:
        raise CaseNotFound(case_id)
    state = json.loads(row["state_json"])
    memo = state.get("risk_memo")
    decision = state.get("human_decision")
    trace = [AgentTrace.model_validate(t) for t in state.get("trace", [])]
    status = _row_status(row)
    return CaseResult(
        case_id=row["case_id"],
        entity_name=row["entity_name"],
        status=status,  # type: ignore[arg-type]
        risk_memo=RiskMemo.model_validate(memo) if memo else None,
        review_reasons=_review_reasons_from_trace(trace) if status == "awaiting_review" else [],
        human_decision=HumanDecision.model_validate(decision) if decision else None,
        trace=trace,
    )


def list_cases(*, pending: bool = False, db_path: Path = config.CASE_STORE_DB_PATH) -> list[CaseSummary]:
    rows = case_store.list_cases(pending_human_review=pending or None, db_path=db_path)
    return [
        CaseSummary(
            case_id=r["case_id"],
            entity_name=r["entity_name"],
            risk_score=r["risk_score"],
            risk_level=r["risk_level"],
            recommended_action=r["recommended_action"],
            status=_row_status(r),  # type: ignore[arg-type]
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]


def check_store(db_path: Path = config.CASE_STORE_DB_PATH) -> None:
    """Raises if the case store cannot be opened (used by /health)."""

    case_store.list_cases(db_path=db_path)
