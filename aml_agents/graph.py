"""Builds the LangGraph graph — the one place that decides who talks to whom
and why.

PLACEHOLDER — see PROJECT_PLAN.md Phase 9, section "graph.py", for the full
requirements: the exact node set, the exact edges (also diagrammed in
ARCHITECTURE.md), the routing precedence rules for route_after_critic, and
how to compile with/without a checkpointer.

    START -> planner -> entity_resolution -> adverse_media -> retrieval
          -> risk_analyst -> critic --[revise, retries left]--> risk_analyst
                                    --[approved, low risk]-----> END
                                    --[high risk, or retries exhausted]--> human_gate -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from typing import Literal
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from aml_agents import config
from aml_agents.nodes.adverse_media import adverse_media_node
from aml_agents.nodes.critic import critic_node
from aml_agents.nodes.entity_resolution import entity_resolution_node
from aml_agents.nodes.human_gate import human_gate_node
from aml_agents.nodes.planner import planner_node
from aml_agents.nodes.retrieval import retrieval_node
from aml_agents.nodes.risk_analyst import risk_analyst_node
from aml_agents.schemas import CaseState, make_trace


def mark_human_review_required(state: CaseState) -> dict:
    return {
        "human_review_required": True,
        **make_trace(
            node_name="mark_human_review_required",
            summary_out="Human review required; pausing before human_gate.",
        ),
    }


def route_after_retrieval(state: CaseState) -> str:
    plan = state.get("plan")

    if plan is None or "risk_analyst" in plan.steps:
        return "risk_analyst"

    return "__end__"


def route_after_evidence_gathering(state: CaseState) -> str:
    """the conditional edge attached to **both** `entity_resolution` and
    `adverse_media` (the fan-in point; see R4 below for why one router function
    on two source nodes is safe and still runs its destination exactly once).
    Pure function of `state["plan"]` only — never of which branch called it, so
    both calls always agree on a destination for a given run.
    1. `state["plan"]` is `None`, or `"retrieval" in plan.steps` -> return
    `"retrieval"`. A missing plan defaults to "run everything", the same
    convention `planner.build_static_plan` uses for its own step list.
    2. Otherwise, if `"risk_analyst" in plan.steps` -> return `"risk_analyst"`
    (retrieval explicitly skipped).
    3. Otherwise -> return `"__end__"` (plan calls for neither)."""

    plan = state['plan']

    if plan is None or 'retrieval' in plan.steps:
        return "retrieval" 
    if 'risk_analyst' in plan.steps:
        return "risk_analyst"

    return "__end__"


def route_after_critic(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 9): pure function of state -> one of
    "risk_analyst" / "human_gate" / "__end__". See PROJECT_PLAN.md for the
    exact precedence order (revise-with-retries-left beats everything else,
    then retries-exhausted/low-confidence/high-risk all route to human_gate,
    otherwise end) — getting the order right matters, not just the
    individual conditions.
    """
    feedback = state.get("critic_feedback")
    memo = state.get("risk_memo")
    revision_count = state.get("revision_count", 0)

    if feedback is not None and feedback.verdict == 'revise' and state['revision_count'] < config.MAX_REVISIONS: # type: ignore
        return 'risk_analyst'
    
    retries_exhausted = feedback is not None and feedback.verdict == "revise"
    low_confidence = feedback is not None and feedback.confidence < config.CRITIC_MIN_CONFIDENCE
    high_risk = memo is not None and memo.risk_score >= config.RISK_ESCALATION_THRESHOLD

    if retries_exhausted or low_confidence or high_risk:
        return "human_gate"

    return "__end__"


def build_graph(checkpointer=None):
    """TODO (PROJECT_PLAN.md Phase 9): construct a StateGraph(CaseState),
    add all 7 nodes, wire the fixed edges planner->entity_resolution->
    adverse_media->retrieval->risk_analyst->critic, add a conditional edge
    out of "critic" using route_after_critic, add human_gate->END, and
    compile — passing checkpointer and interrupt_before=["human_gate"] only
    when a checkpointer is given (so tests can compile without one).
    """

    aml_investigator_graph_builder = StateGraph(CaseState)

    aml_investigator_graph_builder.add_node("planner", planner_node)
    aml_investigator_graph_builder.add_node("entity_resolution", entity_resolution_node)
    aml_investigator_graph_builder.add_node("adverse_media", adverse_media_node)
    aml_investigator_graph_builder.add_node("retrieval", retrieval_node)
    aml_investigator_graph_builder.add_node("risk_analyst", risk_analyst_node)
    aml_investigator_graph_builder.add_node("critic", critic_node)
    aml_investigator_graph_builder.add_node("human_gate", human_gate_node)
    aml_investigator_graph_builder.add_node("mark_human_review_required", mark_human_review_required)

    aml_investigator_graph_builder.add_edge(START, "planner")
    aml_investigator_graph_builder.add_edge("planner", "entity_resolution")
    aml_investigator_graph_builder.add_edge("planner", "adverse_media")
    for source in ["entity_resolution", "adverse_media"]:
        aml_investigator_graph_builder.add_conditional_edges(
                source,
                route_after_evidence_gathering,
                {
                    "retrieval": "retrieval",
                    "risk_analyst": "risk_analyst",
                    "__end__": END

                }
            )
    aml_investigator_graph_builder.add_conditional_edges(
        "retrieval",
        route_after_retrieval,
        {
            "risk_analyst": "risk_analyst",
            "__end__": END,
        },
    )
    aml_investigator_graph_builder.add_edge("risk_analyst", "critic")
    aml_investigator_graph_builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "risk_analyst": "risk_analyst",
            "human_gate": "mark_human_review_required",
            "__end__": END,
        },
    )
    aml_investigator_graph_builder.add_edge("mark_human_review_required", "human_gate")
    aml_investigator_graph_builder.add_edge("human_gate", END)

    if checkpointer is None:
        aml_investigator_graph = aml_investigator_graph_builder.compile()
    else:
        aml_investigator_graph = aml_investigator_graph_builder.compile(checkpointer=checkpointer, 
                                                                        interrupt_before=["human_gate"])

    return aml_investigator_graph