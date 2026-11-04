"""Turn pipeline output (CaseState) into deepeval `LLMTestCase`s.

Everything a metric needs is placed on the test case so metrics stay pure
functions of the test case:

- `actual_output`      -> the memo narrative (what the Risk Analyst wrote).
- `retrieval_context`  -> the evidence the analyst was given, rendered the
                          same way `risk_analyst._format_evidence` renders it.
                          Faithfulness and G-Eval grade the narrative against
                          this, so the judge sees what the analyst saw.
- `metadata`           -> plain facts for the deterministic metrics (expected
                          labels, evidence IDs, citations, routing flags).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from deepeval.test_case import LLMTestCase

from aml_agents.schemas import CaseState

_NO_CANDIDATES = "Sanctions screening returned no candidates above the match threshold."
_NO_MEDIA = "Adverse media search returned no relevant hits."
_NO_GUIDANCE = "No regulatory guidance passages were retrieved."


@dataclass
class CaseRun:
    """One evaluated case: the golden-case label plus what the system produced."""

    index: int
    case: Mapping[str, Any]
    state: CaseState | None
    error: str | None = None
    paused: bool = False  # graph stopped at human_gate waiting for a decision

    @property
    def duration_ms(self) -> float | None:
        if self.state is None:
            return None
        durations = [t.duration_ms for t in self.state.get("trace", []) if t.duration_ms is not None]
        return sum(durations) if durations else None


def expected_human_review(case: Mapping[str, Any]) -> bool:
    """Policy for the golden set: an entity that should resolve to a sanctions
    hit must reach a human; a clean entity must not. Stated here, once, so the
    labels in test_cases.py don't need a second column that can drift.
    """

    return bool(case["expected_entity_resolved"])


def evidence_items(state: CaseState) -> list[tuple[str, str]]:
    """(evidence id, rendered text) for every item the analyst could cite."""

    items: list[tuple[str, str]] = []
    for c in state.get("entity_candidates", []):
        items.append(
            (
                c.source_id,
                f"[{c.source_id}] sanctions candidate {c.matched_name!r} on {c.source_list}, "
                f"match score {c.match_score:.1f}, programme {c.program or 'unknown'}, "
                f"country {c.country or 'unknown'}",
            )
        )
    for h in state.get("adverse_media_findings", []):
        items.append((h.source, f"[{h.source}] adverse media: {h.title}: {h.snippet}"))
    for p in state.get("regulatory_context", []):
        items.append((p.source_document, f"[{p.source_document}] regulatory guidance: {p.text}"))
    return items


def retrieval_context(state: CaseState) -> list[str]:
    """Evidence strings for the judge, with an explicit line for each empty
    section so a narrative saying "no matches found" can be verified."""

    texts = [text for _, text in evidence_items(state)]
    if not state.get("entity_candidates"):
        texts.append(_NO_CANDIDATES)
    if not state.get("adverse_media_findings"):
        texts.append(_NO_MEDIA)
    if not state.get("regulatory_context"):
        texts.append(_NO_GUIDANCE)
    return texts


def run_metadata(run: CaseRun) -> dict[str, Any]:
    state = run.state
    memo = state.get("risk_memo") if state else None
    critic = state.get("critic_feedback") if state else None
    return {
        "case_index": run.index,
        "category": run.case.get("category"),
        "expected_entity_resolved": run.case.get("expected_entity_resolved"),
        "expected_human_review": (
            expected_human_review(run.case) if "expected_entity_resolved" in run.case else None
        ),
        "expected_verdict": run.case.get("expected_verdict"),
        "error": run.error,
        "paused": run.paused,
        "entity_resolved": state.get("entity_resolved") if state else None,
        "human_review_required": state.get("human_review_required") if state else None,
        "candidate_scores": [c.match_score for c in state.get("entity_candidates", [])] if state else [],
        "evidence_ids": [i for i, _ in evidence_items(state)] if state else [],
        # Candidates and media hits are findings the memo must cite; guidance
        # passages are background a "nothing found" memo need not cite.
        "findings_count": (
            len(state.get("entity_candidates", [])) + len(state.get("adverse_media_findings", [])) if state else 0
        ),
        "has_memo": memo is not None,
        "citations": list(memo.citations) if memo else [],
        "risk_score": memo.risk_score if memo else None,
        "risk_level": memo.risk_level if memo else None,
        "recommended_action": memo.recommended_action if memo else None,
        "actual_verdict": critic.verdict if critic else None,
        "critic_issues": list(critic.issues) if critic else [],
    }


def to_test_case(run: CaseRun) -> LLMTestCase:
    state = run.state
    memo = state.get("risk_memo") if state else None
    return LLMTestCase(
        name=f"case-{run.index}",
        input=(state or {}).get("original_query") or f"Investigate entity: {run.case['entity_name']}",
        actual_output=memo.narrative if memo else "(no memo produced)",
        retrieval_context=retrieval_context(state) if state else [_NO_CANDIDATES, _NO_MEDIA, _NO_GUIDANCE],
        metadata=run_metadata(run),
    )
