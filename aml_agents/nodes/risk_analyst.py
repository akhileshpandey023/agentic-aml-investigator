"""Risk Analyst agent — the first LLM-reasoning node.

PLACEHOLDER — see PROJECT_PLAN.md Phase 7, section "risk_analyst.py", for
the full requirements: the evidence-formatting format, the system-prompt
content requirements, the parsing/validation/retry behaviour, and the
revision_count bookkeeping this node owns.

Reads:  state["entity_name"], state["entity_candidates"], state["adverse_media_findings"],
        state["regulatory_context"], state["critic_feedback"] (if this is a revision)
Writes: state["risk_memo"], state["revision_count"], state["trace"]
"""

from __future__ import annotations

from aml_agents.schemas import CaseState, RiskMemo


def _format_evidence(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 7): render CaseState's evidence
    (entity_candidates, adverse_media_findings, regulatory_context, and
    critic_feedback if present) into a plain-text prompt block.
    """
    labelled_evidence = ''
    return labelled_evidence


def _parse_risk_memo(raw_text: str, entity_name: str) -> RiskMemo:  
    """TODO: json.loads raw_text, default entity_name, RiskMemo.model_validate.
    Let json.JSONDecodeError / pydantic.ValidationError propagate — the node
    decides whether to retry.
    """

    raise NotImplementedError("_parse_risk_memo: see PROJECT_PLAN.md Phase 7")


def risk_analyst_node(state: CaseState) -> dict:
    """TODO (PROJECT_PLAN.md Phase 7): format evidence, write a system
    prompt, call aml_agents.llm_client.get_llm_client().complete(...), parse
    the response (consider one retry on malformed JSON), increment
    revision_count if this is a revision, and return
    {"risk_memo": ..., "revision_count": ..., **make_trace(...)}.
    """

    raise NotImplementedError("risk_analyst_node: see PROJECT_PLAN.md Phase 7")
