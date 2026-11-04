"""deepeval metrics for the AML investigator.

Two kinds, deliberately separated:

1. Deterministic metrics (`BaseMetric` subclasses, no LLM). Used wherever the
   right answer is checkable by code: did entity resolution match the label,
   did the case reach a human, are the citations real, does the memo obey the
   scoring policy. They are free, repeatable and never flaky, so they are the
   ones to gate on.
2. LLM-judged metrics (`FaithfulnessMetric`, `GEval`). Used only for what code
   cannot check: whether the narrative's claims are supported by the evidence
   and whether it states its gaps honestly. These depend on the judge model;
   treat them as a trend signal, not a gate, until you have calibrated the
   judge against hand labels (see EVAL_PLAN.md).

The scoring policy is read from `prompts.risk_policy.RISK_BANDS`, the same text
both agents are prompted with, so the checker cannot drift from the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from deepeval.metrics import BaseMetric, FaithfulnessMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from aml_agents import config
from aml_agents.prompts.risk_policy import RISK_BANDS

# --------------------------------------------------------------------------
# Policy, parsed from the prompt text (single source of truth)
# --------------------------------------------------------------------------

_BAND_RE = re.compile(r'-\s*(\d+)\s*-\s*(\d+)\s*->\s*risk_level\s*"(\w+)",\s*recommended_action\s*"(\w+)"')
_FLOOR_MATCH_RE = re.compile(r"match_score\s*>=\s*(\d+)")
_FLOOR_SCORE_RE = re.compile(r"floor\s+of\s+risk_score\s+at\s+(\d+)")


@dataclass(frozen=True)
class Policy:
    bands: tuple[tuple[int, int, str, str], ...]  # (low, high, risk_level, action)
    sanctions_match_score: int  # a candidate at or above this is a "confirmed" match
    sanctions_floor: int  # ...and then risk_score must be at least this

    def expected(self, risk_score: int) -> tuple[str, str] | None:
        for low, high, level, action in self.bands:
            if low <= risk_score <= high:
                return level, action
        return None


def load_policy(text: str = RISK_BANDS) -> Policy:
    """Parse RISK_BANDS. Raises ValueError if its wording changes enough that
    the checker would silently stop checking."""

    bands = tuple((int(a), int(b), lvl, act) for a, b, lvl, act in _BAND_RE.findall(text))
    match, floor = _FLOOR_MATCH_RE.search(text), _FLOOR_SCORE_RE.search(text)
    if not bands or not match or not floor:
        raise ValueError("Could not parse risk bands from RISK_BANDS; update deepeval_metrics.load_policy.")
    return Policy(bands, int(match.group(1)), int(floor.group(1)))


# --------------------------------------------------------------------------
# Deterministic metrics
# --------------------------------------------------------------------------


class _DeterministicMetric(BaseMetric):
    """Boilerplate for a pass/fail metric computed from test_case.metadata."""

    metric_name = "Deterministic"

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.async_mode = False
        self.include_reason = True
        self.strict_mode = False
        self.verbose_mode = False

    def _check(self, md: dict[str, Any]) -> tuple[float, str]:
        raise NotImplementedError

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        md = test_case.metadata or {}
        if md.get("error"):
            self.score, self.reason = 0.0, f"run failed: {md['error']}"
        else:
            self.score, self.reason = self._check(md)
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self) -> str:  # type: ignore[override]
        return self.metric_name


class EntityResolutionMatch(_DeterministicMetric):
    """entity_resolved agrees with the golden label."""

    metric_name = "Entity Resolution Match"

    def _check(self, md):
        expected, actual = md["expected_entity_resolved"], md["entity_resolved"]
        return (1.0 if bool(actual) == bool(expected) else 0.0), f"expected={expected} actual={actual}"


class EscalationRouting(_DeterministicMetric):
    """The case reached (or avoided) the human gate as the policy requires:
    a sanctions hit must reach a human regardless of the LLM's score."""

    metric_name = "Escalation Routing"

    def _check(self, md):
        expected, actual = md["expected_human_review"], md["human_review_required"]
        return (1.0 if bool(actual) == bool(expected) else 0.0), (
            f"expected human review={expected} actual={actual} (risk_score={md['risk_score']})"
        )


class CitationValidity(_DeterministicMetric):
    """Every citation in the memo is an evidence ID the analyst was given, and
    a memo that has findings (sanctions candidates or adverse media) cites
    something. An independent audit of the check the Critic is prompted to do."""

    metric_name = "Citation Validity"

    def _check(self, md):
        if not md["has_memo"]:
            return 0.0, "no memo produced"
        evidence, cited = set(md["evidence_ids"]), md["citations"]
        if not cited:
            if md["findings_count"]:
                return 0.0, "memo cites nothing although findings exist"
            return 1.0, "no findings, no citations needed"
        invalid = [c for c in cited if c not in evidence]
        score = (len(cited) - len(invalid)) / len(cited)
        return score, (f"citations not in evidence: {invalid}" if invalid else "all citations match evidence")


class PolicyConsistency(_DeterministicMetric):
    """risk_level and recommended_action match risk_score under the bands, and
    a confirmed sanctions match respects the score floor."""

    metric_name = "Policy Consistency"

    def __init__(self, threshold: float = 1.0, policy: Policy | None = None):
        super().__init__(threshold)
        self.policy = policy or load_policy()

    def _check(self, md):
        if not md["has_memo"]:
            return 0.0, "no memo produced"
        score, problems = md["risk_score"], []
        expected = self.policy.expected(score)
        if expected is None:
            problems.append(f"risk_score {score} is outside every band")
        elif (md["risk_level"], md["recommended_action"]) != expected:
            problems.append(
                f"score {score} requires {expected}, memo has {(md['risk_level'], md['recommended_action'])}"
            )
        if any(s >= self.policy.sanctions_match_score for s in md["candidate_scores"]) and score < self.policy.sanctions_floor:
            problems.append(
                f"confirmed sanctions match (>= {self.policy.sanctions_match_score}) "
                f"but score {score} < floor {self.policy.sanctions_floor}"
            )
        return (0.0, "; ".join(problems)) if problems else (1.0, "bands and floor respected")


class CriticVerdictMatch(_DeterministicMetric):
    """The Critic's verdict equals the known-correct one for a seeded memo."""

    metric_name = "Critic Verdict Match"

    def _check(self, md):
        expected, actual = md["expected_verdict"], md["actual_verdict"]
        return (1.0 if actual == expected else 0.0), f"expected={expected} actual={actual}"


ENTITY_METRICS = [EntityResolutionMatch]
E2E_DETERMINISTIC_METRICS = [EntityResolutionMatch, EscalationRouting, CitationValidity, PolicyConsistency]
CRITIC_METRICS = [CriticVerdictMatch]


# --------------------------------------------------------------------------
# LLM-judged metrics
# --------------------------------------------------------------------------

_GAP_CRITERIA = (
    "The actual output is an AML risk memo narrative. It must state plainly when "
    "evidence is missing or thin. Where the retrieval context says no sanctions "
    "candidates, no adverse media or no guidance were found, the narrative must say "
    "so and must not describe findings that do not exist. Penalise any narrative that "
    "fills a gap with inference or outside knowledge."
)
_STRENGTH_CRITERIA = (
    "The actual output is an AML risk memo narrative. Judge whether it describes "
    "match strength honestly. A sanctions candidate with a match score below 90 must "
    "not be called confirmed or definite. A name match must not be presented as proof "
    "of identity. Adverse media that only names the entity must not be described as "
    "proof of financial crime. Score high only if every strength claim is calibrated "
    "to the scores and snippets in the retrieval context."
)
_PARAMS = [SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT]


def build_llm_metrics(judge: Any) -> list[BaseMetric]:
    """LLM-judged metrics for cases that produced a memo."""

    common = dict(model=judge, async_mode=False, verbose_mode=False)
    return [
        FaithfulnessMetric(threshold=config.EVAL_FAITHFULNESS_THRESHOLD, include_reason=True, **common),
        GEval(
            name="Gap Disclosure", criteria=_GAP_CRITERIA, evaluation_params=_PARAMS,
            threshold=config.EVAL_GEVAL_THRESHOLD, **common,
        ),
        GEval(
            name="Match Strength Calibration", criteria=_STRENGTH_CRITERIA, evaluation_params=_PARAMS,
            threshold=config.EVAL_GEVAL_THRESHOLD, **common,
        ),
    ]
