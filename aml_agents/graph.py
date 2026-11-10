"""Builds the LangGraph graph — the one place that decides who talks to whom
and why. See PROJECT_PLAN.md Phase 9 and ARCHITECTURE.md.

    START -> planner --(plan.steps)--> entity_resolution and/or adverse_media  (run in parallel)
          -> retrieval -> risk_analyst -> critic
                 critic --[revise, retries left]----------------------> risk_analyst
                 critic --[no escalation reason]----------------------> END
                 critic --[any escalation reason]--> mark_human_review_required
                                                   -> (pause) -> human_gate -> END

Pausing: the graph is always compiled with a checkpointer (an in-memory one
when the caller passes none) and `interrupt_before=["human_gate"]`, so a case
that needs a human stops there and `invoke` returns. Resume it by recording a
`human_decision` with `update_state` and invoking with `None` (see
main.cmd_resume). With the default in-memory saver the pause only lasts as
long as the process; pass a SqliteSaver for cases that outlive it. Any
checkpointer needs a `thread_id` in the invoke config.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from aml_agents import config
from aml_agents.checkpointing import new_memory_saver
from aml_agents.nodes.adverse_media import adverse_media_node
from aml_agents.nodes.critic import critic_node
from aml_agents.nodes.entity_resolution import entity_resolution_node
from aml_agents.nodes.human_gate import human_gate_node
from aml_agents.nodes.planner import planner_node
from aml_agents.nodes.retrieval import retrieval_node
from aml_agents.nodes.risk_analyst import risk_analyst_node
from aml_agents.policy import has_confirmed_match
from aml_agents.schemas import CaseState, make_trace

EVIDENCE_NODES = ("entity_resolution", "adverse_media")


def escalation_reasons(state: CaseState) -> list[str]:
    """Why this case must go to a human, empty if it need not. Every reason is
    a deterministic function of state, not of anything the LLM was merely asked
    to do: a confirmed sanctions match reaches a human even if the analyst
    scored it low.
    """

    feedback = state.get("critic_feedback")
    memo = state.get("risk_memo")
    reasons: list[str] = []

    if feedback is not None and feedback.verdict == "revise":
        reasons.append("critic still requesting revisions after the retry limit")
    if feedback is not None and feedback.confidence < config.CRITIC_MIN_CONFIDENCE:
        reasons.append(f"critic confidence {feedback.confidence:.2f} below {config.CRITIC_MIN_CONFIDENCE}")
    if memo is None:
        reasons.append("no risk memo was produced")
    elif memo.risk_score >= config.RISK_ESCALATION_THRESHOLD:
        reasons.append(f"risk_score {memo.risk_score} at or above {config.RISK_ESCALATION_THRESHOLD}")
    if has_confirmed_match(state.get("entity_candidates", [])):
        reasons.append(f"confirmed sanctions match (score >= {config.SANCTIONS_CONFIRMED_MATCH_SCORE})")
    return reasons


def mark_human_review_required(state: CaseState) -> dict:
    """Runs just before the pause, so the checkpointed state already says why
    the case is waiting (human_review_required, and the reasons in the trace).
    human_gate_node itself runs only after a decision is recorded."""

    reasons = escalation_reasons(state)
    return {
        "human_review_required": True,
        **make_trace(
            node_name="mark_human_review_required",
            summary_out="Human review required: " + ("; ".join(reasons) or "unspecified") + ". Pausing before human_gate.",
        ),
    }


def _after_evidence(state: CaseState) -> str:
    """Where to go once evidence gathering is finished or skipped."""

    plan = state.get("plan")
    if plan is None or "retrieval" in plan.steps:
        return "retrieval"
    if "risk_analyst" in plan.steps:
        return "risk_analyst"
    return "__end__"


def route_after_planner(state: CaseState) -> list[str]:
    """Start only the evidence nodes the plan asks for (all of them when there
    is no plan). If it asks for neither, skip straight to what comes next."""

    plan = state.get("plan")
    if plan is None:
        return list(EVIDENCE_NODES)
    selected = [node for node in EVIDENCE_NODES if node in plan.steps]
    return selected or [_after_evidence(state)]


def route_after_evidence_gathering(state: CaseState) -> str:
    """Conditional edge on both evidence nodes (the fan-in point). A pure
    function of `state["plan"]`, never of which branch called it, so both
    calls agree and the destination runs once per superstep.

    No plan, or "retrieval" in the plan -> "retrieval"; else "risk_analyst" if
    planned; else "__end__".
    """

    return _after_evidence(state)


def route_after_retrieval(state: CaseState) -> str:
    plan = state.get("plan")
    if plan is None or "risk_analyst" in plan.steps:
        return "risk_analyst"
    return "__end__"


def route_after_critic(state: CaseState) -> str:
    """Pure function of state -> "risk_analyst" | "human_gate" | "__end__".

    Precedence: a revise verdict with retries left beats everything; after
    that any escalation reason (see escalation_reasons) goes to the human gate;
    otherwise the case ends.
    """

    feedback = state.get("critic_feedback")
    if feedback is not None and feedback.verdict == "revise" and state.get("revision_count", 0) < config.MAX_REVISIONS:
        return "risk_analyst"
    return "human_gate" if escalation_reasons(state) else "__end__"


def build_graph(checkpointer=None):
    """Construct and compile the investigation graph (see module docstring)."""

    builder = StateGraph(CaseState)

    builder.add_node("planner", planner_node)
    builder.add_node("entity_resolution", entity_resolution_node)
    builder.add_node("adverse_media", adverse_media_node)
    builder.add_node("retrieval", retrieval_node)
    builder.add_node("risk_analyst", risk_analyst_node)
    builder.add_node("critic", critic_node)
    builder.add_node("mark_human_review_required", mark_human_review_required)
    builder.add_node("human_gate", human_gate_node)

    builder.add_edge(START, "planner")
    destinations = {
        "entity_resolution": "entity_resolution",
        "adverse_media": "adverse_media",
        "retrieval": "retrieval",
        "risk_analyst": "risk_analyst",
        "__end__": END,
    }
    builder.add_conditional_edges("planner", route_after_planner, destinations)
    for source in EVIDENCE_NODES:
        builder.add_conditional_edges(
            source,
            route_after_evidence_gathering,
            {"retrieval": "retrieval", "risk_analyst": "risk_analyst", "__end__": END},
        )
    builder.add_conditional_edges(
        "retrieval", route_after_retrieval, {"risk_analyst": "risk_analyst", "__end__": END}
    )
    builder.add_edge("risk_analyst", "critic")
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {"risk_analyst": "risk_analyst", "human_gate": "mark_human_review_required", "__end__": END},
    )
    builder.add_edge("mark_human_review_required", "human_gate")
    builder.add_edge("human_gate", END)

    return builder.compile(
        checkpointer=checkpointer if checkpointer is not None else new_memory_saver(),
        interrupt_before=["human_gate"],
    )
