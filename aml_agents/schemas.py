"""Shared contracts — GIVEN, not part of the exercise.

Every agent's input and output is a Pydantic model defined here, and
`CaseState` is the single TypedDict that flows through the LangGraph graph.
These are given on purpose: every placeholder function you'll implement
elsewhere is specified in terms of these exact field names, so a stable,
provided contract is what keeps the scaffolding internally consistent while
you fill in the logic behind it. (This is itself the Phase 1 lesson — see
PROJECT_PLAN.md — even though there's no code for you to write here: read
this file closely before touching anything else.)
"""

from __future__ import annotations

import operator
import time
import uuid
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

# --------------------------------------------------------------------------
# Evidence models — one per specialist agent's output
# --------------------------------------------------------------------------


class EntityMatch(BaseModel):
    """One candidate match from the Entity Resolution agent."""

    matched_name: str
    source_list: Literal["us_ofac_sdn", "gb_hmt_sanctions"]
    source_id: str = Field(description="The list's own unique ID for this entry")
    match_score: float = Field(ge=0, le=100, description="Fuzzy-match similarity score")
    program: Optional[str] = Field(default=None, description="Sanctions programme, e.g. 'RUSSIA'")
    country: Optional[str] = None


class AdverseMediaHit(BaseModel):
    """One relevant hit from the Adverse Media agent's search."""

    title: str
    snippet: str
    source: str = Field(description="Document filename or URL")
    published_date: Optional[str] = None
    relevance_score: float = Field(ge=0, le=1)


class RetrievedPassage(BaseModel):
    """One passage returned by the Retrieval (RAG) agent."""

    text: str
    source_document: str
    section: Optional[str] = None
    score: float = Field(description="Post-rerank relevance score")


# --------------------------------------------------------------------------
# Reasoning models — planner / risk analyst / critic / human gate
# --------------------------------------------------------------------------


class InvestigationPlan(BaseModel):
    """Output of the Planner agent."""

    steps: list[Literal["entity_resolution", "adverse_media", "retrieval", "risk_analyst"]]
    rationale: str = Field(description="Why these steps, in this order, for this case")


class RiskMemo(BaseModel):
    """Output of the Risk Analyst agent — the actual case memo."""

    entity_name: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high", "critical"]
    narrative: str = Field(description="The analyst write-up")
    recommended_action: Literal["clear", "escalate", "file_sar"]
    citations: list[str] = Field(
        description="Each citation should point at a specific piece of evidence already in "
        "CaseState (an EntityMatch.source_id, an AdverseMediaHit.source, or a "
        "RetrievedPassage.source_document) — never a claim with no traceable source."
    )


class CriticReview(BaseModel):
    """Output of the Critic agent."""

    verdict: Literal["approve", "revise"]
    confidence: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list, description="Specific, actionable problems found")
    notes: str = ""


class HumanDecision(BaseModel):
    """Recorded outcome of the Human Gate."""

    decision: Literal["confirm", "override_clear", "override_escalate"]
    reviewer: str
    notes: str = ""
    decided_at: float = Field(default_factory=time.time)


class AgentTrace(BaseModel):
    """One observability record, appended by every node (see ARCHITECTURE.md)."""

    node_name: str
    timestamp: float = Field(default_factory=time.time)
    summary_in: str = ""
    summary_out: str = ""
    duration_ms: Optional[float] = None
    token_usage: Optional[dict[str, int]] = None


# --------------------------------------------------------------------------
# Shared graph state
# --------------------------------------------------------------------------


class CaseState(TypedDict):
    """The single object every LangGraph node reads from and writes to.

    Field ownership (which node is expected to set each field):

        case_id, entity_name, original_query  -> set once, at graph invocation
        plan                                   -> planner
        entity_candidates, entity_resolved     -> entity_resolution
        adverse_media_findings                 -> adverse_media
        regulatory_context                     -> retrieval
        risk_memo                              -> risk_analyst
        critic_feedback                        -> critic
        revision_count                         -> risk_analyst (incremented when revising)
        human_review_required                  -> human_gate (True iff this node ran)
        human_decision                         -> human_gate
        trace                                  -> every node (appends)
    """

    case_id: str
    entity_name: str
    original_query: str

    plan: Optional[InvestigationPlan]

    entity_candidates: list[EntityMatch]
    entity_resolved: bool

    adverse_media_findings: list[AdverseMediaHit]

    regulatory_context: list[RetrievedPassage]

    risk_memo: Optional[RiskMemo]

    critic_feedback: Optional[CriticReview]
    revision_count: int

    human_review_required: bool
    human_decision: Optional[HumanDecision]

    # Annotated with operator.add so each node's trace entries accumulate
    # instead of overwriting each other under LangGraph's default
    # last-write-wins state update behaviour — every other field overwrites,
    # only this one appends.
    trace: Annotated[list[AgentTrace], operator.add]


def new_case_state(entity_name: str, original_query: str | None = None, case_id: str | None = None) -> CaseState:
    """Build an empty, valid CaseState to kick off a graph run. GIVEN."""

    return CaseState(
        case_id=case_id or str(uuid.uuid4()),
        entity_name=entity_name, 
        original_query=original_query or f"Investigate entity: {entity_name}",
        plan=None,
        entity_candidates=[],
        entity_resolved=False,
        adverse_media_findings=[],
        regulatory_context=[],
        risk_memo=None,
        critic_feedback=None,
        revision_count=0,
        human_review_required=False,
        human_decision=None,
        trace=[],
    )


def make_trace(node_name: str, summary_in: str = "", summary_out: str = "", duration_ms: float | None = None,
                token_usage: dict[str, int] | None = None) -> dict[str, Any]:
    """Convenience for the common `return {"trace": [make_trace(...)]}` pattern
    at the end of every node you implement. GIVEN.
    """

    return {
        "trace": [
            AgentTrace(
                node_name=node_name,
                summary_in=summary_in,
                summary_out=summary_out,
                duration_ms=duration_ms,
                token_usage=token_usage,
            )
        ]
    }
