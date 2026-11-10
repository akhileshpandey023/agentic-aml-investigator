"""Regression tests for the review fixes (one or more per fixed issue)."""

import json

import pytest

from aml_agents import config
from aml_agents.checkpointing import new_memory_saver
from aml_agents.graph import build_graph, escalation_reasons, route_after_critic
from aml_agents.llm_client import LocalOpenAICompatLLMClient
from aml_agents.nodes import risk_analyst
from aml_agents.policy import apply_policy, band_for
from aml_agents.schemas import CriticReview, EntityMatch, RiskMemo, new_case_state
from aml_agents.tools import adverse_media_search, sanctions_lookup


def _memo(score, level="high", action="escalate"):
    return RiskMemo(entity_name="X", risk_score=score, risk_level=level, narrative="n",
                    recommended_action=action, citations=[])


def _match(score):
    return EntityMatch(matched_name="X", source_list="us_ofac_sdn", source_id="1", match_score=score)


# policy
def test_band_edges():
    assert band_for(24).risk_level == "low" and band_for(25).risk_level == "medium"
    assert band_for(90).recommended_action == "file_sar"


def test_policy_floors_confirmed_sanctions_match():
    memo, notes = apply_policy(_memo(10, "low", "clear"), [_match(95)])
    assert memo.risk_score == config.SANCTIONS_RISK_FLOOR and memo.recommended_action == "escalate"
    assert notes


def test_policy_corrects_level_and_action_to_band():
    memo, _ = apply_policy(_memo(95, "low", "clear"), [])
    assert (memo.risk_level, memo.recommended_action) == ("critical", "file_sar")


# routing
def test_confirmed_match_reaches_human_even_if_scored_low():
    state = new_case_state("X")
    state["risk_memo"] = _memo(5, "low", "clear")
    state["critic_feedback"] = CriticReview(verdict="approve", confidence=0.95)
    state["entity_candidates"] = [_match(97)]
    assert route_after_critic(state) == "human_gate"
    assert escalation_reasons(state)


def test_revise_with_retries_left_goes_to_analyst():
    state = new_case_state("X")
    state["risk_memo"] = _memo(80)
    state["critic_feedback"] = CriticReview(verdict="revise", confidence=0.9, issues=["x"])
    state["revision_count"] = 0
    assert route_after_critic(state) == "risk_analyst"


def test_graph_always_has_pause_point():
    app = build_graph()
    assert "human_gate" in app.interrupt_before_nodes


def test_checkpointer_roundtrips_models():
    saver = new_memory_saver()
    typ, data = saver.serde.dumps_typed({"m": _memo(1)})
    assert saver.serde.loads_typed((typ, data))["m"].risk_score == 1


# risk analyst parsing / retry
def test_extract_json_from_fence():
    assert json.loads(risk_analyst._extract_json_text('```json\n{"a": 1}\n```')) == {"a": 1}


def test_risk_analyst_retries_then_succeeds(monkeypatch):
    good = _memo(80).model_dump_json()
    replies = iter(["not json", good])

    class Fake:
        def complete(self, system, user, **kw):
            from aml_agents.llm_client import LLMResponse
            return LLMResponse(text=next(replies), input_tokens=1, output_tokens=1)

    monkeypatch.setattr(risk_analyst, "get_llm_client", lambda: Fake())
    out = risk_analyst.risk_analyst_node(new_case_state("X"))
    assert out["risk_memo"].risk_score == 80 and out["revision_count"] == 0


# sanctions lookup
def _csv(tmp_path, monkeypatch, rows):
    path = tmp_path / "us_ofac_sdn.csv"
    path.write_text("id,name,aliases,program_ids,countries\n" + rows)
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", path)
    sanctions_lookup._load_list.cache_clear()


def test_lookup_is_case_insensitive_and_matches_aliases(tmp_path, monkeypatch):
    _csv(tmp_path, monkeypatch, "1,ELIAV LIBI,Eli Libi;E. Libi,RUSSIA,ru\n")
    hits = sanctions_lookup.lookup("Eliav Libi", source_lists=("us_ofac_sdn",))
    assert hits and hits[0].match_score >= config.ENTITY_MATCH_MIN_SCORE
    alias_hits = sanctions_lookup.lookup("Eli Libi", source_lists=("us_ofac_sdn",))
    assert len(alias_hits) == 1  # one result per entry, not per alias
    sanctions_lookup._load_list.cache_clear()


def test_corrupt_file_is_not_reported_as_missing(tmp_path, monkeypatch):
    path = tmp_path / "us_ofac_sdn.csv"
    path.write_bytes(b"")
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", path)
    sanctions_lookup._load_list.cache_clear()
    with pytest.raises(ValueError):
        sanctions_lookup._load_list("us_ofac_sdn")
    sanctions_lookup._load_list.cache_clear()


# adverse media
def test_adverse_media_requires_full_name(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("Marta Ellison was fined for failing AML controls.")
    (tmp_path / "b.txt").write_text("Marta Smith, compliance officer, joined the firm. Marta Smith spoke.")
    monkeypatch.setattr(config, "FCA_NOTICES_DIR", tmp_path)
    adverse_media_search._load_corpus.cache_clear()
    hits = adverse_media_search.search("Marta Ellison")
    assert [h.source for h in hits] == ["a.txt"]
    assert adverse_media_search.search("Nobody Atall") == []
    adverse_media_search._load_corpus.cache_clear()


# local LLM client
def test_local_client_uses_openai_endpoint(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": "hi"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2}}

    def fake_post(url, json=None, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        return R()

    monkeypatch.setattr("aml_agents.llm_client.requests.post", fake_post)
    for base in ("http://h:1", "http://h:1/", "http://h:1/v1"):
        resp = LocalOpenAICompatLLMClient(base, "m").complete("s", "u")
        assert seen["url"] == "http://h:1/v1/chat/completions" and seen["timeout"]
        assert (resp.text, resp.input_tokens, resp.output_tokens) == ("hi", 3, 2)


def test_memo_entity_name_comes_from_case():
    memo = risk_analyst._parse_risk_memo(_memo(10).model_dump_json(), "Real Name")
    assert memo.entity_name == "Real Name"
