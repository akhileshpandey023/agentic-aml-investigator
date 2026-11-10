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
import json
import time
from pydantic import ValidationError
import re

from aml_agents.llm_client import get_llm_client
from aml_agents.policy import apply_policy
from aml_agents.prompts import RISK_ANALYST_PROMPT
from aml_agents.schemas import CaseState, RiskMemo, make_trace

MAX_ATTEMPTS = 3  # LLM calls per memo when the output is malformed


def _format_evidence(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 7): render CaseState's evidence
    (entity_candidates, adverse_media_findings, regulatory_context, and
    critic_feedback if present) into a plain-text prompt block.
    """
    entity_resolution_prompt: list[str] = [f'{state['entity_name']}', '']

    entity_resolution_prompt.append('SANCTIONS SCREENING CANDIDATES:')
    if state['entity_candidates']:
        for cand in state['entity_candidates']:
            entity_resolution_prompt.append(f''' - [source id: {cand.source_id}], matched entity name: {cand.matched_name} 
            source list: {cand.source_list},  entity matching score: {cand.match_score:.1f}, program: {cand.program}
            ''')
    else:
        entity_resolution_prompt.append('No matching entity founds with score above threshold')

    entity_resolution_prompt.append('ADVERSE MEDIA SCREENING: ')
    if state['adverse_media_findings']:
        for amh in state['adverse_media_findings']:
            entity_resolution_prompt.append(f''' - [source: {amh.source}] {amh.title}: {amh.snippet}''')
    else:
        entity_resolution_prompt.append('No adverse media hits found')

    entity_resolution_prompt.append('REGULATORY GUIDANCE DOC:')
    if state['regulatory_context']:
        for rc in state['regulatory_context']:
            entity_resolution_prompt.append(f''' - [source document: {rc.source_document}] regulatory text: {rc.text}, ''')
    else:
        entity_resolution_prompt.append('No regulatory guidance found')

    feedback = state.get("critic_feedback")
    if feedback is not None:
        entity_resolution_prompt.append("")
        entity_resolution_prompt.append("PRIOR CRITIC FEEDBACK TO ADDRESS (this is a revision, not a fresh draft):")
        for issue in feedback.issues:
            entity_resolution_prompt.append(f"  - {issue}")
        previous = state.get("risk_memo")
        if previous is not None:
            entity_resolution_prompt.append("")
            entity_resolution_prompt.append("YOUR PREVIOUS MEMO (revise this; do not start from nothing):")
            entity_resolution_prompt.append(json.dumps(previous.model_dump(), indent=2))

    return '\n'.join(entity_resolution_prompt)


def _extract_json_text(raw_text: str) -> str:
    """Strip a markdown code fence if the model wrapped its JSON in one."""

    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, flags=re.DOTALL)
    return (match.group(1) if match else raw_text).strip()


def _parse_risk_memo(raw_text: str, entity_name: str) -> RiskMemo:
    """json.loads raw_text, default entity_name, RiskMemo.model_validate.
    json.JSONDecodeError / pydantic.ValidationError propagate; the node
    decides whether to retry.
    """

    payload = json.loads(_extract_json_text(raw_text))
    payload.setdefault("entity_name", entity_name)
    return RiskMemo.model_validate(payload)


def _summarise_input(state: CaseState, is_revision: bool) -> str:
    """A short, fixed-size description of what this node was given. The trace
    is stored in the case state and the case store, so it must not embed the
    state itself (which contains the trace, and so grows with every node)."""

    return (
        f"entity={state['entity_name']!r} candidates={len(state['entity_candidates'])} "
        f"adverse_media={len(state['adverse_media_findings'])} passages={len(state['regulatory_context'])} "
        f"revision={is_revision}"
    )


def risk_analyst_node(state: CaseState) -> dict:
    """Format the evidence, call the LLM (up to MAX_ATTEMPTS tries on malformed
    output, feeding the parse error back), apply the scoring policy, and
    return {"risk_memo", "revision_count", "trace"}. Raises after the last
    failed attempt rather than returning no memo.
    """

    start_time = time.perf_counter()
    evidence_found = _format_evidence(state)
    system_prompt = RISK_ANALYST_PROMPT
    risk_memo: RiskMemo | None = None
    llm_response = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        llm_response = get_llm_client().complete(system=system_prompt, user=evidence_found)
        try:
            risk_memo = _parse_risk_memo(llm_response.text, state["entity_name"])
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            system_prompt = (
                RISK_ANALYST_PROMPT
                + f"\n\nYour previous reply could not be used: {exc}\nReturn only the corrected JSON object."
            )

    assert risk_memo is not None and llm_response is not None  # loop either breaks with a memo or raises
    risk_memo, policy_notes = apply_policy(risk_memo, state["entity_candidates"])

    is_revision = state.get("critic_feedback") is not None
    revision_count = state.get("revision_count", 0) + 1 if is_revision else 0
    duration_ms = (time.perf_counter() - start_time) * 1000

    summary_out = f"{risk_memo}"
    if policy_notes:
        summary_out += " | policy adjustments: " + "; ".join(policy_notes)
    return {
        "risk_memo": risk_memo,
        "revision_count": revision_count,
        **make_trace(
            node_name="risk_analyst",
            summary_in=_summarise_input(state, is_revision),
            summary_out=summary_out,
            token_usage={
                "input_token": int(llm_response.input_tokens or 0),
                "output_token": int(llm_response.output_tokens or 0),
            },
            duration_ms=duration_ms,
        ),
    }
