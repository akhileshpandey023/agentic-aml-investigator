"""Human Gate.

PLACEHOLDER — see PROJECT_PLAN.md Phase 9, section "human_gate_node", which
also explains the LangGraph interrupt/resume mechanism this node depends on.

Reads:  state["human_decision"], state["risk_memo"]
Writes: state["risk_memo"] (recommended_action may be overridden),
        state["human_review_required"] (set True), state["trace"]
"""

from __future__ import annotations
import time

from aml_agents.schemas import CaseState, make_trace


def human_gate_node(state: CaseState) -> dict:
    """TODO: read state["human_decision"] (raise RuntimeError with a clear
    message if it's None — see PROJECT_PLAN.md Phase 9 for why that
    shouldn't normally happen), apply override_clear/override_escalate to
    risk_memo.recommended_action via model_copy(update=...) (leave it alone
    on "confirm"), and return
    {"risk_memo": ..., "human_review_required": True, **make_trace(...)}.
    """

    start_time = time.perf_counter()
    memo = state['risk_memo']
    if state['human_decision'] is None:
        raise RuntimeError(
            "human_gate_node reached without a recorded human_decision — the graph "
            "should have paused before this node ran. Check the interrupt_before "
            "wiring in graph.py."
        )
    updated_memo = memo
    if state['risk_memo']:
        if state['human_decision'].decision == 'override_clear':
            updated_memo = state['risk_memo'].model_copy(update={'recommended_action':'clear'})
        elif state['human_decision'].decision=='override_escalate':
            updated_memo = state['risk_memo'].model_copy(update={'recommended_action':'escalate'})
    
    end_time = time.perf_counter()
    
    return {"risk_memo": updated_memo, 
            "human_review_required": True, 
            **make_trace(node_name='human_gate',
                         summary_in="decision={decision.decision!r} by {decision.reviewer!r}",
                         summary_out=f"final recommended_action={updated_memo.recommended_action if updated_memo else None}",
                         duration_ms=(end_time-start_time)*1000
                         ),
                         }
