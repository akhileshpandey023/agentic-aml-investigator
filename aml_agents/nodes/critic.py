"""Critic agent — the reflection/evaluator half of the evaluator-generator loop.

PLACEHOLDER — see PROJECT_PLAN.md Phase 8, section "critic.py", for the full
requirements: what groundedness and consistency checks the prompt must
cover, and the parsing behaviour.

Reads:  state["risk_memo"], state["entity_candidates"], state["adverse_media_findings"],
        state["regulatory_context"]
Writes: state["critic_feedback"], state["trace"]

Note on revision_count ownership: this node only judges (approve/revise).
risk_analyst.py owns incrementing revision_count; graph.py's router only
reads it. See ARCHITECTURE.md design principle 3.
"""

from __future__ import annotations
import json
import time

from aml_agents.schemas import CaseState, CriticReview, make_trace
from aml_agents.llm_client import get_llm_client

from aml_agents.prompts import CRITIC_PROMPT

def _format_review_context(state: CaseState) -> str:
    """TODO (PROJECT_PLAN.md Phase 8): render state["risk_memo"] (as JSON)
    alongside the same evidence risk_analyst saw, so the critic can check
    groundedness, not just internal consistency.
    """
    critic_review_prompt = []
    risk_memo = state["risk_memo"]
    if risk_memo:
        try:
            risk_memo = json.dumps(risk_memo.model_dump(), indent=2) # type: ignore
        except:
            risk_memo = 'no memo produced'
    else:
        risk_memo = 'no memo produced'

    critic_review_prompt.append(risk_memo)

    critic_review_prompt.append('SANCTIONS SCREENING CANDIDATES:')
    if state['entity_candidates']:
        for re in state['entity_candidates']:
            critic_review_prompt.append(f''' - [source id: {re.source_id}], 
            matched entity name: {re.matched_name}, entity matching score: {re.match_score:.1f}
            ''')
    else:
        critic_review_prompt.append(' (none)')

    critic_review_prompt.append('ADVERSE MEDIA SCREENING: ')
    if state['adverse_media_findings']:
        for amh in state['adverse_media_findings']:
            critic_review_prompt.append(f''' - [source: {amh.source}] {amh.title}''')
    else:
        critic_review_prompt.append(' (none)')

    critic_review_prompt.append('REGULATORY GUIDANCE DOC:')
    if state['regulatory_context']:
        for rc in state['regulatory_context']:
            critic_review_prompt.append(f''' - [source document: {rc.source_document}]''')
    else:
        critic_review_prompt.append(' (none)')
    
    return '\n '.join(critic_review_prompt)


def _parse_critic_review(raw_text: str) -> CriticReview: 
    """TODO: json.loads + CriticReview.model_validate."""

    return CriticReview.model_validate(json.loads(raw_text))


def critic_node(state: CaseState) -> dict:
    """TODO (PROJECT_PLAN.md Phase 8): format the review context, write a
    system prompt covering groundedness + consistency checks, call the LLM,
    parse the response, and return
    {"critic_feedback": ..., **make_trace(...)}.
    """
    start_time = time.perf_counter()
    cr_context = _format_review_context(state)
    llm_response = get_llm_client().complete(system=CRITIC_PROMPT, user=cr_context)
    parsed_review = _parse_critic_review(llm_response['text']) # type: ignore
    end_time = time.perf_counter()

    return {"critic_feedback": parsed_review, 
            **make_trace(
                node_name='risk_analyst',
                summary_in=f"{state}",
                token_usage={'input_token': int(llm_response.input_tokens), 'output_token': int(llm_response.output_tokens)}, # type: ignore
                summary_out=f"{parsed_review}",
                            duration_ms=(end_time-start_time)*1000
                            ),
                            }
