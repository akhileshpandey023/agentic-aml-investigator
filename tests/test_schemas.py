"""GIVEN. schemas.py is provided, so these pass immediately — a sanity check
that your environment is set up correctly before you start Phase 2.
"""

import pytest
from pydantic import ValidationError

from aml_agents.schemas import RiskMemo, make_trace, new_case_state


def test_new_case_state_defaults():
    state = new_case_state(entity_name="Test Entity")
    assert state["entity_name"] == "Test Entity"
    assert state["entity_resolved"] is False
    assert state["entity_candidates"] == []
    assert state["revision_count"] == 0
    assert state["trace"] == []
    assert "Test Entity" in state["original_query"]


def test_new_case_state_custom_query_and_id():
    state = new_case_state(entity_name="X", original_query="custom query", case_id="abc-123")
    assert state["case_id"] == "abc-123"
    assert state["original_query"] == "custom query"


def test_make_trace_shape():
    update = make_trace("planner", summary_in="in", summary_out="out", duration_ms=1.5)
    assert list(update.keys()) == ["trace"]
    assert len(update["trace"]) == 1
    entry = update["trace"][0]
    assert entry.node_name == "planner"
    assert entry.duration_ms == 1.5


def test_risk_memo_rejects_invalid_action():
    with pytest.raises(ValidationError):
        RiskMemo(
            entity_name="X",
            risk_score=50,
            risk_level="medium",
            narrative="...",
            recommended_action="do_nothing",  # not a valid Literal value
            citations=[],
        )


def test_risk_memo_valid():
    memo = RiskMemo(
        entity_name="X",
        risk_score=90,
        risk_level="critical",
        narrative="...",
        recommended_action="file_sar",
        citations=["us_ofac_sdn:12345"],
    )
    assert memo.risk_score == 90
