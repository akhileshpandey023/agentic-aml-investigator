"""Planner agent.

PLACEHOLDER — see PROJECT_PLAN.md Phase 6, section "planner.py", for the
static-plan requirements, and Phase 13 for the optional dynamic-plan
stretch exercise.

Reads:  state["entity_name"], state["original_query"]
Writes: state["plan"], state["trace"]
"""

from __future__ import annotations

from aml_agents.schemas import CaseState, InvestigationPlan, make_trace
import time


def build_static_plan(state: CaseState) -> InvestigationPlan: 
    """TODO (PROJECT_PLAN.md Phase 6): return an InvestigationPlan with
    steps=["entity_resolution", "adverse_media", "retrieval", "risk_analyst"]
    and a short rationale string.
    """
    return InvestigationPlan(steps=['entity_resolution', 'adverse_media', 'retrieval', 'risk_analyst'],
                             rationale='static plan steps for entity')


def build_dynamic_plan(state: CaseState) -> InvestigationPlan:  
    """TODO (Phase 13, stretch — see PROJECT_PLAN.md): have an LLM choose
    `steps` from state["original_query"] alone, using the same
    "prompt + parse + validate" shape as risk_analyst_node. Not called by
    build_static_plan or planner_node by default.
    """

    raise NotImplementedError("build_dynamic_plan is a Phase 13 stretch exercise")


def planner_node(state: CaseState) -> dict:
    """TODO: call build_static_plan, time it, and return
    {"plan": ..., **make_trace(...)}.
    """
    start_time = time.perf_counter()
    static_plan = build_static_plan(state)
    end_time = time.perf_counter()

    return {
        'plan': static_plan, 
        **make_trace(
            node_name='planner_node',
            summary_in=state['entity_name'],
            summary_out=(
                f"Steps created in teh plan: {static_plan.steps}"
                ),
                duration_ms=(end_time-start_time)*1000
                ),
            }
