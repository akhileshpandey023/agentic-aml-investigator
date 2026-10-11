"""Human Gate.

PLACEHOLDER — see PROJECT_PLAN.md Phase 9, section "human_gate_node", which
also explains the LangGraph interrupt/resume mechanism this node depends on.

Reads:  state["human_decision"], state["risk_memo"]
Writes: state["risk_memo"] (recommended_action may be overridden),
        state["human_review_required"] (set True), state["trace"]
"""

from __future__ import annotations

from aml_agents.schemas import CaseState


def human_gate_node(state: CaseState) -> dict:
    """TODO: read state["human_decision"] (raise RuntimeError with a clear
    message if it's None — see PROJECT_PLAN.md Phase 9 for why that
    shouldn't normally happen), apply override_clear/override_escalate to
    risk_memo.recommended_action via model_copy(update=...) (leave it alone
    on "confirm"), and return
    {"risk_memo": ..., "human_review_required": True, **make_trace(...)}.
    """

    raise NotImplementedError("human_gate_node: see PROJECT_PLAN.md Phase 9")
