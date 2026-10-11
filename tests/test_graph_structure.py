"""GIVEN — your Phase 9 acceptance criteria. Structural tests only: they
check the graph is wired the way ARCHITECTURE.md/PROJECT_PLAN.md describe,
without invoking any node (risk_analyst/critic make real LLM calls once
implemented — this file deliberately doesn't need network access or
downloaded data). All of these fail with NotImplementedError until you
implement aml_agents/graph.py. Your goal is to turn this file green without
editing it.
"""

from aml_agents import config
from aml_agents.graph import build_graph, route_after_critic
from aml_agents.schemas import CriticReview, RiskMemo, new_case_state

EXPECTED_NODES = {
    "planner",
    "entity_resolution",
    "adverse_media",
    "retrieval",
    "risk_analyst",
    "critic",
    "human_gate",
}


def test_graph_compiles_without_checkpointer():
    app = build_graph(checkpointer=None)
    assert hasattr(app, "invoke")


def test_graph_has_all_expected_nodes():
    app = build_graph(checkpointer=None)
    node_names = set(app.get_graph().nodes.keys()) - {"__start__", "__end__"}
    assert EXPECTED_NODES <= node_names, f"missing nodes: {EXPECTED_NODES - node_names}"


def _memo(risk_score: int) -> RiskMemo:
    return RiskMemo(
        entity_name="X", risk_score=risk_score, risk_level="high", narrative="...",
        recommended_action="escalate", citations=[],
    )


def test_router_sends_low_risk_approved_to_end():
    state = new_case_state("X")
    state["risk_memo"] = _memo(risk_score=10)
    state["critic_feedback"] = CriticReview(verdict="approve", confidence=0.95)
    assert route_after_critic(state) == "__end__"


def test_router_sends_high_risk_approved_to_human_gate():
    state = new_case_state("X")
    state["risk_memo"] = _memo(risk_score=config.RISK_ESCALATION_THRESHOLD)
    state["critic_feedback"] = CriticReview(verdict="approve", confidence=0.95)
    assert route_after_critic(state) == "human_gate"


def test_router_sends_revise_with_retries_left_back_to_risk_analyst():
    state = new_case_state("X")
    state["risk_memo"] = _memo(risk_score=10)
    state["critic_feedback"] = CriticReview(verdict="revise", confidence=0.9, issues=["fabricated citation"])
    state["revision_count"] = 0
    assert route_after_critic(state) == "risk_analyst"


def test_router_escalates_once_revisions_exhausted():
    state = new_case_state("X")
    state["risk_memo"] = _memo(risk_score=10)
    state["critic_feedback"] = CriticReview(verdict="revise", confidence=0.9, issues=["still wrong"])
    state["revision_count"] = config.MAX_REVISIONS
    assert route_after_critic(state) == "human_gate"


def test_router_escalates_on_low_confidence_even_if_approved():
    state = new_case_state("X")
    state["risk_memo"] = _memo(risk_score=10)
    state["critic_feedback"] = CriticReview(verdict="approve", confidence=0.1)
    assert route_after_critic(state) == "human_gate"
