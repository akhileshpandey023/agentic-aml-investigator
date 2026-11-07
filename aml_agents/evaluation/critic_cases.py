"""Seeded memos for measuring the Critic: known-good controls and memos with
one deliberate defect each. The evidence is synthetic and self-contained (a
fictional entity, fictional IDs), so these cases need no downloaded data and
the right verdict is known by construction.

The Critic is measured on two rates (see metrics.critic_rates):
  catch rate           -> fraction of defective memos it sends back ("revise")
  false-positive rate  -> fraction of clean memos it wrongly sends back
A critic that always says "revise" has a perfect catch rate and is useless, so
neither number means anything without the other.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from aml_agents.schemas import (
    AdverseMediaHit,
    CaseState,
    EntityMatch,
    RetrievedPassage,
    RiskMemo,
    new_case_state,
)

ENTITY = "Vostok Trading LLC"
OFAC_ID = "TEST-OFAC-1001"
MEDIA_SRC = "fca_notices/notice_001.txt"
GUIDE_SRC = "guidance/jmlsg_sanctions.txt"


class CriticCase(TypedDict):
    entity_name: str
    category: Literal["critic_control", "critic_defect"]
    expected_verdict: Literal["approve", "revise"]
    defect: str
    state: CaseState


def _state(*, match_score: float | None, media: bool, memo: RiskMemo) -> CaseState:
    state = new_case_state(ENTITY)
    if match_score is not None:
        state["entity_candidates"] = [
            EntityMatch(
                matched_name=ENTITY, source_list="us_ofac_sdn", source_id=OFAC_ID,
                match_score=match_score, program="RUSSIA", country="ru",
            )
        ]
        state["entity_resolved"] = match_score >= 85
    if media:
        state["adverse_media_findings"] = [
            AdverseMediaHit(
                title="Final Notice: sanctions-controls failings", source=MEDIA_SRC,
                snippet="The firm processed payments for a customer without screening them.",
                relevance_score=1.0,
            )
        ]
    state["regulatory_context"] = [
        RetrievedPassage(
            text="Firms must screen customers against the financial sanctions lists before onboarding.",
            source_document=GUIDE_SRC, score=0.9,
        )
    ]
    state["risk_memo"] = memo
    return state


def _memo(score: int, level: str, action: str, narrative: str, citations: list[str]) -> RiskMemo:
    return RiskMemo(
        entity_name=ENTITY, risk_score=score, risk_level=level,  # type: ignore[arg-type]
        recommended_action=action, narrative=narrative, citations=citations,  # type: ignore[arg-type]
    )


def build_critic_cases() -> list[CriticCase]:
    good_hit = _memo(
        92, "critical", "file_sar",
        f"The entity matches sanctions entry {OFAC_ID} on us_ofac_sdn (RUSSIA programme) with a "
        f"match score of 100. Adverse media in {MEDIA_SRC} records sanctions-controls failings by a firm. "
        f"Guidance in {GUIDE_SRC} requires screening before onboarding.",
        [OFAC_ID, MEDIA_SRC, GUIDE_SRC],
    )
    good_clear = _memo(
        5, "low", "clear",
        "No sanctions candidates were found above the threshold, no adverse media was found, and no "
        "guidance was retrieved. The evidence does not indicate elevated risk.",
        [],
    )

    def case(name, category, verdict, defect, state):
        return CriticCase(entity_name=name, category=category, expected_verdict=verdict, defect=defect, state=state)

    return [
        case("control_confirmed_hit", "critic_control", "approve", "none",
             _state(match_score=100, media=True, memo=good_hit)),
        case("control_clean", "critic_control", "approve", "none",
             _state(match_score=None, media=False, memo=good_clear)),
        case("fabricated_citation", "critic_defect", "revise", "cites an ID that is not in the evidence",
             _state(match_score=100, media=True,
                    memo=good_hit.model_copy(update={"citations": [OFAC_ID, "OFAC-99999", MEDIA_SRC]}))),
        case("overstated_match", "critic_defect", "revise", "calls an 86-score candidate a confirmed match",
             _state(match_score=86, media=False,
                    memo=_memo(75, "high", "escalate",
                               f"This is a confirmed match to sanctions entry {OFAC_ID}, proving the entity is sanctioned.",
                               [OFAC_ID]))),
        case("band_violation", "critic_defect", "revise", "risk_level and action disagree with the score",
             _state(match_score=100, media=True,
                    memo=good_hit.model_copy(update={"risk_score": 85, "risk_level": "low", "recommended_action": "clear"}))),
        case("sanctions_floor_violation", "critic_defect", "revise", "confirmed match scored below the 70 floor",
             _state(match_score=100, media=False,
                    memo=_memo(40, "medium", "clear",
                               f"The entity matches {OFAC_ID} with a match score of 100.", [OFAC_ID]))),
        case("unsupported_claim", "critic_defect", "revise", "states a listing date and alias absent from the evidence",
             _state(match_score=100, media=False,
                    memo=_memo(92, "critical", "file_sar",
                               f"The entity matches {OFAC_ID}. It was designated in March 2022 and trades under the "
                               "alias Vostok Maritime, as shown in the listing.", [OFAC_ID]))),
        case("gap_not_disclosed", "critic_defect", "revise", "describes adverse media where the section is empty",
             _state(match_score=None, media=False,
                    memo=_memo(55, "medium", "escalate",
                               "Adverse media alleges the entity facilitated sanctions evasion, per "
                               f"guidance in {GUIDE_SRC}.", [GUIDE_SRC]))),
    ]
