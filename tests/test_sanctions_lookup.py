"""GIVEN — this is your Phase 2 acceptance criteria. All of these will fail
with NotImplementedError until you implement aml_agents/tools/sanctions_lookup.py
(see PROJECT_PLAN.md Phase 2). Your goal is to turn this file green without
editing it.
"""

import pandas as pd
import pytest

from aml_agents.tools import sanctions_lookup


@pytest.fixture
def fixture_sanctions_dir(tmp_path, monkeypatch):
    """Writes a tiny fake sanctions CSV and points sanctions_lookup at it,
    instead of requiring the real (large, downloaded) OpenSanctions files.
    """

    df = pd.DataFrame(
        [
            {"id": "US-1", "name": "Vostok Trading LLC", "program_ids": "sanction", "countries": "ru"},
            {"id": "US-2", "name": "Anatoly Ivanovich Petrov", "program_ids": "sanction", "countries": "ru"},
        ]
    )
    us_csv = tmp_path / "us_ofac_sdn.csv"
    df.to_csv(us_csv, index=False)

    gb_csv = tmp_path / "gb_hmt_sanctions.csv"
    pd.DataFrame([{"id": "GB-1", "name": "Nordwind Shipping Ltd", "program_ids": "sanction", "countries": "gb"}]).to_csv(
        gb_csv, index=False
    )

    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", us_csv)
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "gb_hmt_sanctions", gb_csv)
    sanctions_lookup._load_list.cache_clear()
    yield
    sanctions_lookup._load_list.cache_clear()


def test_exact_match_scores_high(fixture_sanctions_dir):
    results = sanctions_lookup.lookup("Vostok Trading LLC")
    assert results
    assert results[0].matched_name == "Vostok Trading LLC"
    assert results[0].match_score >= 95


def test_no_match_for_unrelated_name(fixture_sanctions_dir):
    results = sanctions_lookup.lookup(
        "Alderbrook Community Bakery Ltd", min_score=sanctions_lookup.config.ENTITY_MATCH_MIN_SCORE
    )
    assert results == []


def test_searches_both_lists(fixture_sanctions_dir):
    results = sanctions_lookup.lookup("Nordwind Shipping", min_score=70)
    assert any(r.source_list == "gb_hmt_sanctions" for r in results)


def test_missing_file_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", tmp_path / "does_not_exist.csv")
    sanctions_lookup._load_list.cache_clear()
    with pytest.raises(FileNotFoundError, match="download_public_data.py"):
        sanctions_lookup.lookup("anyone", source_lists=("us_ofac_sdn",))
    sanctions_lookup._load_list.cache_clear()
