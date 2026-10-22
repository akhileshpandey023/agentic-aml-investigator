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

from aml_agents.schemas import CaseState, RiskMemo, make_trace
from aml_agents.prompts import RISK_ANALYST_PROMPT
from aml_agents.llm_client import get_llm_client


def _format_evidence(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 7): render CaseState's evidence
    (entity_candidates, adverse_media_findings, regulatory_context, and
    critic_feedback if present) into a plain-text prompt block.
    """
    entity_resolution_prompt: list[str] = [f'{state['entity_name']}', '']

    entity_resolution_prompt.append('SANCTIONS SCREENING CANDIDATES:')
    if state['entity_candidates']:
        for re in state['entity_candidates']:
            entity_resolution_prompt.append(f''' - [source id: {re.source_id}], matched entity name: {re.matched_name} 
            source list: {re.source_list},  entity matching score: {re.match_score:.1f}, program: {re.program}
            ''')
    else:
        entity_resolution_prompt.append('No matching entity founds with score above threshold')

    entity_resolution_prompt.append('ADVERSE MEDIA SCREENING: ')
    if state['adverse_media_findings']:
        for amh in state['adverse_media_findings']:
            entity_resolution_prompt.append(f''' - [source: {amh.source}] {amh.title}: {amh.snippet}''')
    else:
        entity_resolution_prompt.append(f'No adverse media hits found')

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

    return '\n'.join(entity_resolution_prompt)


def _parse_risk_memo(raw_text: str, entity_name: str) -> RiskMemo:  
    """TODO: json.loads raw_text, default entity_name, RiskMemo.model_validate.
    Let json.JSONDecodeError / pydantic.ValidationError propagate — the node
    decides whether to retry.
    """
    payload = json.loads(raw_text)
    payload.setdefault("entity_name", entity_name)

    return RiskMemo.model_validate(payload)


def risk_analyst_node(state: CaseState) -> dict:
    """TODO (PROJECT_PLAN.md Phase 7): format evidence, write a system
    prompt, call aml_agents.llm_client.get_llm_client().complete(...), parse
    the response (consider one retry on malformed JSON), increment
    revision_count if this is a revision, and return
    {"risk_memo": ..., "revision_count": ..., **make_trace(...)}.
    """
    start_time = time.perf_counter()
    evidence_found = _format_evidence(state)
    risk_memo = None
    attempt = 1
    while attempt < 3:
        try:
            llm_response = get_llm_client().complete(system=RISK_ANALYST_PROMPT, user=evidence_found)
            risk_memo = _parse_risk_memo(llm_response['text'], state['entity_name']) # type: ignore
        except (json.JSONDecodeError, ValidationError) as e:
            attempt += 1
            llm_response = get_llm_client().complete(system=RISK_ANALYST_PROMPT + f'Address the exception {e} to ensure output is correct', 
                                                     user=evidence_found)
            risk_memo = _parse_risk_memo(llm_response['text'], state['entity_name']) # type: ignore

    state['risk_memo'] = risk_memo
    
    if state['critic_feedback'] is not None:
        is_revision = True
    else:
        is_revision = False
    state['revision_count'] = state.get('revision_count', 0) + 1 if is_revision else 0
    end_time = time.perf_counter()

    return {"risk_memo": risk_memo, 
            "revision_count": state['revision_count'], 
            **make_trace(
                node_name='risk_analyst',
                summary_in=f"{state}",
                token_usage={'input_token': int(llm_response.input_tokens), 'output_token': int(llm_response.output_tokens)}, # type: ignore
                summary_out=f"{risk_memo}",
                            duration_ms=(end_time-start_time)*1000
                            ),
                            }
