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

from aml_agents import config
from aml_agents.nodes.adverse_media import adverse_media_node
from aml_agents.nodes.critic import critic_node
from aml_agents.nodes.entity_resolution import entity_resolution_node
from aml_agents.nodes.human_gate import human_gate_node
from aml_agents.nodes.planner import planner_node
from aml_agents.nodes.retrieval import retrieval_node
from aml_agents.nodes.risk_analyst import risk_analyst_node
from aml_agents.schemas import CaseState


def route_after_critic(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 9): pure function of state -> one of
    "risk_analyst" / "human_gate" / "__end__". See PROJECT_PLAN.md for the
    exact precedence order (revise-with-retries-left beats everything else,
    then retries-exhausted/low-confidence/high-risk all route to human_gate,
    otherwise end) — getting the order right matters, not just the
    individual conditions.
    """

    raise NotImplementedError("route_after_critic: see PROJECT_PLAN.md Phase 9")


def build_graph(checkpointer=None):
    """TODO (PROJECT_PLAN.md Phase 9): construct a StateGraph(CaseState),
    add all 7 nodes, wire the fixed edges planner->entity_resolution->
    adverse_media->retrieval->risk_analyst->critic, add a conditional edge
    out of "critic" using route_after_critic, add human_gate->END, and
    compile — passing checkpointer and interrupt_before=["human_gate"] only
    when a checkpointer is given (so tests can compile without one).
    """

    raise NotImplementedError("build_graph: see PROJECT_PLAN.md Phase 9")
