"""The risk-scoring policy, as code.

One definition of the score bands and the sanctions floor, used by:
  - prompts/risk_policy.py, which renders it into the Risk Analyst and Critic
    prompts, so the model is told exactly what the code enforces;
  - risk_analyst_node, which applies it to the model's memo (the LLM is told
    the rules, but hard rules are not left to the LLM);
  - graph.route_after_critic, which uses has_confirmed_match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from aml_agents import config
from aml_agents.schemas import EntityMatch, RiskMemo


@dataclass(frozen=True)
class Band:
    low: int
    high: int
    risk_level: str
    recommended_action: str


BANDS: tuple[Band, ...] = (
    Band(0, 24, "low", "clear"),
    Band(25, 49, "medium", "clear"),
    Band(50, 69, "medium", "escalate"),
    Band(70, 89, "high", "escalate"),
    Band(90, 100, "critical", "file_sar"),
)


def band_for(score: int) -> Band:
    score = max(0, min(100, int(score)))
    return next(b for b in BANDS if b.low <= score <= b.high)


def has_confirmed_match(candidates: Iterable[EntityMatch]) -> bool:
    return any(c.match_score >= config.SANCTIONS_CONFIRMED_MATCH_SCORE for c in candidates)


def apply_policy(memo: RiskMemo, candidates: Iterable[EntityMatch]) -> tuple[RiskMemo, list[str]]:
    """Return (memo conforming to the policy, notes on what was changed).

    1. A confirmed sanctions match floors risk_score at SANCTIONS_RISK_FLOOR.
    2. risk_level and recommended_action are the band for the (final) score.
    Anything changed is reported in `notes` so it shows up in the trace and the
    adjustment is never silent.
    """

    notes: list[str] = []
    score = memo.risk_score
    if has_confirmed_match(candidates) and score < config.SANCTIONS_RISK_FLOOR:
        notes.append(f"risk_score {score} raised to sanctions floor {config.SANCTIONS_RISK_FLOOR}")
        score = config.SANCTIONS_RISK_FLOOR

    band = band_for(score)
    updates: dict[str, object] = {}
    if score != memo.risk_score:
        updates["risk_score"] = score
    if memo.risk_level != band.risk_level:
        notes.append(f"risk_level {memo.risk_level!r} set to {band.risk_level!r} for score {score}")
        updates["risk_level"] = band.risk_level
    if memo.recommended_action != band.recommended_action:
        notes.append(f"recommended_action {memo.recommended_action!r} set to {band.recommended_action!r} for score {score}")
        updates["recommended_action"] = band.recommended_action
    return (memo.model_copy(update=updates) if updates else memo), notes
