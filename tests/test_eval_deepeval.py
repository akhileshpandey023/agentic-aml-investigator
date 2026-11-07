"""Tests for the deepeval-based evaluation harness. Offline: no real LLM, no
downloaded data. Skipped when the optional `eval` extra is not installed:

    uv sync --extra eval
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest import mock

import pandas as pd
import pytest

pytest.importorskip("deepeval")

from aml_agents import config
from aml_agents.evaluation import deepeval_metrics as dm
from aml_agents.evaluation import eval_store, metrics
from aml_agents.evaluation.adapters import CaseRun, to_test_case
from aml_agents.evaluation.critic_cases import build_critic_cases
from aml_agents.evaluation.judge import LLMClientJudge, extract_json
from aml_agents.evaluation.run_eval import execute
from aml_agents.llm_client import LLMResponse
from aml_agents.schemas import (
    CriticReview,
    EntityMatch,
    InvestigationPlan,
    RiskMemo,
    make_trace,
    new_case_state,
)

# --------------------------------------------------------------------------
# Policy and deterministic metrics
# --------------------------------------------------------------------------


def test_policy_is_parsed_from_the_prompt_text():
    policy = dm.load_policy()
    assert policy.expected(0) == ("low", "clear")
    assert policy.expected(100) == ("critical", "file_sar")
    assert policy.sanctions_match_score == 90 and policy.sanctions_floor == 70
    covered = sorted((low, high) for low, high, _, _ in policy.bands)
    assert covered[0][0] == 0 and covered[-1][1] == 100
    assert all(a[1] + 1 == b[0] for a, b in zip(covered, covered[1:])), "bands must be contiguous"


def test_policy_parse_fails_loudly_on_unrecognised_text():
    with pytest.raises(ValueError):
        dm.load_policy("no bands here")


def _score(metric, run):
    metric.measure(to_test_case(run))
    return metric.score, metric.reason


def test_seeded_critic_cases_are_labelled_correctly_by_the_deterministic_metrics():
    """Guards the seeded cases themselves: a control must pass the code checks,
    and the defects that code can detect must fail them."""

    by_name = {c["entity_name"]: c for c in build_critic_cases()}
    run = lambda name: CaseRun(0, by_name[name], by_name[name]["state"])

    for control in ("control_confirmed_hit", "control_clean"):
        assert _score(dm.CitationValidity(), run(control))[0] == 1.0
        assert _score(dm.PolicyConsistency(), run(control))[0] == 1.0
    assert _score(dm.CitationValidity(), run("fabricated_citation"))[0] < 1.0
    assert _score(dm.PolicyConsistency(), run("band_violation"))[0] == 0.0
    assert _score(dm.PolicyConsistency(), run("sanctions_floor_violation"))[0] == 0.0


def test_citation_validity_scores_fraction_of_real_citations():
    state = [c for c in build_critic_cases() if c["entity_name"] == "fabricated_citation"][0]["state"]
    score, reason = _score(dm.CitationValidity(), CaseRun(0, {"entity_name": "x"}, state))
    assert score == pytest.approx(2 / 3) and "OFAC-99999" in reason


def test_errored_run_scores_zero_with_the_error_as_reason():
    run = CaseRun(0, {"entity_name": "x", "expected_entity_resolved": True}, new_case_state("x"), error="Boom: nope")
    score, reason = _score(dm.EntityResolutionMatch(), run)
    assert score == 0.0 and "Boom" in reason


# --------------------------------------------------------------------------
# Judge adapter
# --------------------------------------------------------------------------


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": 2}} Hope that helps') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json")


class _FakeClient:
    def __init__(self, text):
        self.text = text

    def complete(self, system, user, *, max_tokens=1024, temperature=0.0):
        return LLMResponse(text=self.text, input_tokens=1, output_tokens=1)


def test_judge_returns_schema_instance_or_raw_text():
    from pydantic import BaseModel

    class Verdict(BaseModel):
        verdict: str

    ok = LLMClientJudge(_FakeClient('```json\n{"verdict": "yes"}\n```'), "fake")
    assert ok.generate("p", schema=Verdict) == Verdict(verdict="yes")
    bad = LLMClientJudge(_FakeClient("not json"), "fake")
    assert bad.generate("p", schema=Verdict) == "not json"
    assert bad.generate("p") == "not json"


def test_telemetry_is_opted_out():
    from deepeval.config.settings import get_settings

    assert get_settings().DEEPEVAL_TELEMETRY_OPT_OUT


# --------------------------------------------------------------------------
# eval_store
# --------------------------------------------------------------------------


def test_store_roundtrip_and_compare_runs(tmp_path):
    db = tmp_path / "eval.sqlite"
    a = eval_store.start_run(notes="a", db_path=db)
    b = eval_store.start_run(notes="b", db_path=db)
    eval_store.save_metric(a, "recall", 0.5, db_path=db)
    eval_store.save_metric(b, "recall", 0.75, db_path=db)
    eval_store.save_metric(a, "only_in_a", 1.0, db_path=db)
    eval_store.save_metric(b, "precision", float("nan"), db_path=db)
    rows = {r["metric_name"]: r for r in eval_store.compare_runs(a, b, db_path=db)}
    assert rows["recall"]["diff"] == pytest.approx(0.25)
    assert rows["only_in_a"]["value_b"] is None and rows["only_in_a"]["diff"] is None
    assert rows["precision"]["value_b"] is None  # NaN stored as NULL
    snapshot = json.loads(eval_store.list_runs(db)[0]["config_json"])
    assert snapshot["ENTITY_MATCH_MIN_SCORE"] == config.ENTITY_MATCH_MIN_SCORE


# --------------------------------------------------------------------------
# Runner levels
# --------------------------------------------------------------------------


@pytest.fixture
def fake_sanctions(tmp_path, monkeypatch):
    from aml_agents.tools import sanctions_lookup

    row = {"id": "US-1", "name": "Vostok Trading LLC", "program_ids": "RUSSIA", "countries": "ru"}
    for name in ("us_ofac_sdn", "gb_hmt_sanctions"):
        path = tmp_path / f"{name}.csv"
        pd.DataFrame([row if name == "us_ofac_sdn" else {**row, "id": "GB-1", "name": "Other Corp"}]).to_csv(
            path, index=False
        )
        monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, name, path)
    sanctions_lookup._load_list.cache_clear()
    yield
    sanctions_lookup._load_list.cache_clear()


def test_entity_level_end_to_end(fake_sanctions, tmp_path):
    cases = [
        {"entity_name": "Vostok Trading LLC", "category": "known_sanctioned", "expected_entity_resolved": True, "notes": ""},
        {"entity_name": "Willowbrook Stationery", "category": "clearly_clean", "expected_entity_resolved": False, "notes": ""},
        {"entity_name": "Unmatchable Name Missing", "category": "name_variant", "expected_entity_resolved": True, "notes": ""},
    ]
    db = tmp_path / "eval.sqlite"
    run_id = execute("entity", cases=cases, db_path=db)
    stored = eval_store.get_metrics(run_id, db)
    assert stored["entity_resolution.recall"] == pytest.approx(0.5)
    assert stored["entity_resolution.precision"] == pytest.approx(1.0)
    assert stored["deepeval.Entity Resolution Match.pass_rate"] == pytest.approx(2 / 3)
    assert stored["entity.errors"] == 0


def _stub_nodes(*, boom_for=None, score=85):
    def planner(s):
        return {"plan": InvestigationPlan(steps=["entity_resolution", "adverse_media", "retrieval", "risk_analyst"], rationale="x"), **make_trace("planner")}

    def er(s):
        if s["entity_name"] == boom_for:
            raise RuntimeError("lookup exploded")
        hit = s["entity_name"].startswith("Sanc")
        cands = [EntityMatch(matched_name=s["entity_name"], source_list="us_ofac_sdn", source_id="S-1", match_score=100)] if hit else []
        return {"entity_candidates": cands, "entity_resolved": hit, **make_trace("er", duration_ms=1.0)}

    def am(s):
        return {"adverse_media_findings": [], **make_trace("am")}

    def ret(s):
        return {"regulatory_context": [], **make_trace("ret")}

    def ra(s):
        hit = bool(s["entity_candidates"])
        memo = RiskMemo(
            entity_name=s["entity_name"], risk_score=score if hit else 5,
            risk_level="high" if hit else "low", recommended_action="escalate" if hit else "clear",
            narrative="Sanctions match S-1." if hit else "Nothing found.", citations=["S-1"] if hit else [],
        )
        return {"risk_memo": memo, "revision_count": 0, **make_trace("ra")}

    def cr(s):
        return {"critic_feedback": CriticReview(verdict="approve", confidence=0.9), **make_trace("cr")}

    return dict(planner_node=planner, entity_resolution_node=er, adverse_media_node=am,
                retrieval_node=ret, risk_analyst_node=ra, critic_node=cr)


class _JudgeStub(LLMClientJudge):
    """Answers every deepeval schema request with a passing verdict."""

    def __init__(self):
        super().__init__(_FakeClient(""), "stub-judge")

    def generate(self, prompt, schema=None):
        if schema is None:
            return "ok"
        name, fields = schema.__name__, list(schema.model_fields)
        canned = {"Statements": {"statements": ["s"]}, "Truths": {"truths": ["t"]}, "Claims": {"claims": ["c"]},
                  "Verdicts": {"verdicts": [{"verdict": "yes"}]}, "ReasonScore": {"score": 9, "reason": "grounded"}}
        data = canned.get(name) or {f: ("yes" if f == "verdict" else "ok") for f in fields}
        return schema.model_validate(data)


def test_graph_level_records_failures_and_pauses_and_scores_llm_metrics(tmp_path):
    from aml_agents import graph

    cases = [
        {"entity_name": "Sanctioned Co", "category": "known_sanctioned", "expected_entity_resolved": True, "notes": ""},
        {"entity_name": "Quiet Bakery", "category": "clearly_clean", "expected_entity_resolved": False, "notes": ""},
        {"entity_name": "Explodes Ltd", "category": "clearly_clean", "expected_entity_resolved": False, "notes": ""},
    ]
    db = tmp_path / "eval.sqlite"
    with ExitStack() as stack:
        for name, fn in _stub_nodes(boom_for="Explodes Ltd").items():
            stack.enter_context(mock.patch.object(graph, name, fn))
        run_id = execute("e2e", cases=cases, judge=_JudgeStub(), db_path=db)

    stored = eval_store.get_metrics(run_id, db)
    assert stored["e2e.errors"] == 1  # the failing case is a result, not an abort
    assert stored["e2e.pause_rate"] == pytest.approx(1 / 3)  # only the sanctioned case reached the gate
    assert stored["deepeval.Escalation Routing.pass_rate"] == pytest.approx(2 / 3)
    assert stored["deepeval.Citation Validity.pass_rate"] == pytest.approx(2 / 3)  # failed case scores 0
    # LLM-judged metrics ran, and only for the two cases that produced a memo
    faithfulness = [k for k in stored if k.startswith("deepeval.Faithfulness")]
    assert faithfulness, "judge metrics were not recorded"
    with eval_store._connect(db) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM eval_case_scores WHERE run_id=? AND metric_name='Faithfulness'", (run_id,)
        ).fetchone()[0]
    assert n == 2


def test_critic_level_reports_catch_rate_and_false_positive_rate_together(tmp_path):
    """A critic that always says 'revise' catches everything and is useless;
    the false-positive rate is what exposes it."""

    from aml_agents.nodes import critic

    always_revise = _FakeClient(json.dumps({"verdict": "revise", "confidence": 0.9, "issues": ["x"], "notes": ""}))
    db = tmp_path / "eval.sqlite"
    with mock.patch.object(critic, "get_llm_client", lambda: always_revise):
        run_id = execute("critic", db_path=db)
    stored = eval_store.get_metrics(run_id, db)
    assert stored["critic.catch_rate"] == 1.0
    assert stored["critic.false_positive_rate"] == 1.0


def test_summarise_scores_excludes_errored_evaluations_from_the_mean():
    rows = [
        {"case_index": 0, "metric_name": "m", "score": 1.0, "passed": True, "error": None},
        {"case_index": 1, "metric_name": "m", "score": 0.0, "passed": False, "error": "judge returned bad JSON"},
    ]
    s = metrics.summarise_scores(rows)["m"]
    assert s["mean"] == 1.0 and s["errors"] == 1 and s["n"] == 2
