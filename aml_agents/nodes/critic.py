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
import re

from aml_agents.llm_client import get_llm_client
from aml_agents.prompts import CRITIC_PROMPT
from aml_agents.schemas import CaseState, CriticReview, make_trace

PASSAGE_EXCERPT_CHARS = 600  # per guidance passage shown to the critic

def _format_review_context(state: CaseState) -> str:
    """Render the memo (as JSON) and the same evidence the Risk Analyst saw,
    with the same fields the CRITIC_PROMPT says each section has. The critic
    can only check groundedness against what it is shown, so sanctions
    candidates carry list/score/programme, adverse media carries its snippet and
    guidance carries a text excerpt, not just titles.
    """

    memo = state.get("risk_memo")
    lines = [
        "MEMO UNDER REVIEW:",
        json.dumps(memo.model_dump(), indent=2) if memo else "no memo produced",
        "",
        "EVIDENCE: SANCTIONS CANDIDATES:",
    ]
    candidates = state.get("entity_candidates") or []
    if candidates:
        for c in candidates:
            lines.append(
                f" - [source id: {c.source_id}] matched name: {c.matched_name}; source list: {c.source_list}; "
                f"match score: {c.match_score:.1f}; programme: {c.program or 'unknown'}; country: {c.country or 'unknown'}"
            )
    else:
        lines.append(" (none)")

    lines += ["", "EVIDENCE: ADVERSE MEDIA:"]
    findings = state.get("adverse_media_findings") or []
    if findings:
        for h in findings:
            lines.append(f" - [source: {h.source}] {h.title}: {h.snippet}")
    else:
        lines.append(" (none)")

    lines += ["", "EVIDENCE: REGULATORY GUIDANCE:"]
    passages = state.get("regulatory_context") or []
    if passages:
        for p in passages:
            lines.append(f" - [source document: {p.source_document}] {p.text[:PASSAGE_EXCERPT_CHARS]}")
    else:
        lines.append(" (none)")
    return "\n".join(lines)


def _parse_critic_review(raw_text: str) -> CriticReview:
    """json.loads (tolerating a markdown code fence) + CriticReview.model_validate."""

    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, flags=re.DOTALL)
    return CriticReview.model_validate(json.loads((match.group(1) if match else raw_text).strip()))


def critic_node(state: CaseState) -> dict:
    """Format the review context, call the LLM with CRITIC_PROMPT, parse the
    verdict, and return {"critic_feedback", "trace"}. Raises on an unparseable
    reply, which the graph surfaces as a failed run rather than a silent approve.
    """

    start_time = time.perf_counter()
    llm_response = get_llm_client().complete(system=CRITIC_PROMPT, user=_format_review_context(state))
    parsed_review = _parse_critic_review(llm_response.text)
    memo = state.get("risk_memo")

    return {
        "critic_feedback": parsed_review,
        **make_trace(
            node_name="critic",
            summary_in=f"memo risk_score={memo.risk_score if memo else None} revision_count={state.get('revision_count', 0)}",
            summary_out=f"{parsed_review}",
            token_usage={
                "input_token": int(llm_response.input_tokens or 0),
                "output_token": int(llm_response.output_tokens or 0),
            },
            duration_ms=(time.perf_counter() - start_time) * 1000,
        ),
    }
