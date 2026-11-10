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
    """Apply the reviewer's decision to the memo and record it.

    Runs only after a decision has been recorded: the graph pauses before this
    node (interrupt_before in graph.py), and main.cmd_resume writes
    `human_decision` before resuming. Reaching it without one is a wiring bug,
    so it raises rather than quietly passing the case through.

    An override changes `recommended_action`. The system's own assessment
    (risk_score, risk_level) is left as it was, and the narrative records what
    was overridden and by whom, so the memo never reads as if the system had
    reached the reviewer's conclusion itself.
    """

    start_time = time.perf_counter()
    decision = state.get("human_decision")
    if decision is None:
        raise RuntimeError(
            "human_gate_node reached without a recorded human_decision; the graph "
            "should have paused before this node ran. Check interrupt_before in graph.py."
        )

    memo = state.get("risk_memo")
    updated_memo = memo
    if memo is not None and decision.decision in ("override_clear", "override_escalate"):
        action = "clear" if decision.decision == "override_clear" else "escalate"
        note = (
            f"[Human review by {decision.reviewer}: {decision.decision}. The system had recommended "
            f"{memo.recommended_action!r} at risk_score {memo.risk_score}."
            + (f" Reviewer notes: {decision.notes}" if getattr(decision, "notes", "") else "")
            + "] "
        )
        updated_memo = memo.model_copy(update={"recommended_action": action, "narrative": note + memo.narrative})

    return {
        "risk_memo": updated_memo,
        "human_review_required": True,
        **make_trace(
            node_name="human_gate",
            summary_in=f"decision={decision.decision!r} by {decision.reviewer!r}",
            summary_out=f"final recommended_action={updated_memo.recommended_action if updated_memo else None}",
            duration_ms=(time.perf_counter() - start_time) * 1000,
        ),
    }
