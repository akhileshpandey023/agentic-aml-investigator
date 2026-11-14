"""API tests (Phase 13). No Docker, network or API key: the real graph runs
with a fake LLM, a two-line sanctions list and a stubbed vector store."""

import json

import pytest
from fastapi.testclient import TestClient

from aml_agents import config
from aml_agents.api import create_app
from aml_agents.graph import build_graph
from aml_agents.llm_client import LLMBackendError, LLMResponse
from aml_agents.nodes import critic, retrieval, risk_analyst
from aml_agents.tools import adverse_media_search, sanctions_lookup


class FakeLLM:
    fail = False

    def complete(self, system, user, **kw):
        if self.fail:
            raise LLMBackendError("backend down")
        if "MEMO UNDER REVIEW" in user:
            return LLMResponse(json.dumps({"verdict": "approve", "confidence": 0.9, "issues": []}), 1, 1)
        memo = {"risk_score": 20, "risk_level": "low", "narrative": "n",
                "recommended_action": "clear", "citations": []}
        return LLMResponse(json.dumps(memo), 1, 1)


class NoPassages:
    def query(self, *a, **k):
        return []


@pytest.fixture
def llm(monkeypatch, tmp_path):
    fake = FakeLLM()
    fake.fail = False
    for module in (risk_analyst, critic):
        monkeypatch.setattr(module, "get_llm_client", lambda: fake)
    monkeypatch.setattr(retrieval, "_get_store", lambda: NoPassages())

    sanctions = tmp_path / "s"
    sanctions.mkdir()
    (sanctions / "us.csv").write_text("id,name,program_ids,countries\n1,ACME TRADING LLC,RUSSIA,ru\n")
    (sanctions / "gb.csv").write_text("id,name,program_ids,countries\n")
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", sanctions / "us.csv")
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "gb_hmt_sanctions", sanctions / "gb.csv")
    sanctions_lookup._load_list.cache_clear()

    notices = tmp_path / "n"
    notices.mkdir()
    (notices / "a.txt").write_text("Acme Trading LLC was fined for AML failures.")
    (notices / "b.txt").write_text("An unrelated notice.")
    monkeypatch.setattr(config, "FCA_NOTICES_DIR", notices)
    adverse_media_search._load_corpus.cache_clear()
    yield fake
    sanctions_lookup._load_list.cache_clear()
    adverse_media_search._load_corpus.cache_clear()


@pytest.fixture
def client(llm, tmp_path):
    app = create_app(graph=build_graph(), db_path=tmp_path / "cases.sqlite")
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_clean_entity_completes(client):
    r = client.post("/investigations", json={"entity_name": "Zed Quux Gmbh"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed" and body["risk_memo"]["risk_score"] == 20
    assert body["review_reasons"] == []
    assert client.get(f"/investigations/{body['case_id']}").json()["status"] == "completed"


def test_sanctioned_entity_pauses_then_resumes(client):
    r = client.post("/investigations", json={"entity_name": "Acme Trading LLC"})
    body = r.json()
    assert body["status"] == "awaiting_review"
    assert any("sanctions match" in reason for reason in body["review_reasons"])
    case_id = body["case_id"]

    pending = client.get("/investigations", params={"pending": "true"}).json()
    assert [c["case_id"] for c in pending] == [case_id]
    assert client.get(f"/investigations/{case_id}").json()["status"] == "awaiting_review"

    d = client.post(f"/investigations/{case_id}/decision",
                    json={"decision": "override_clear", "reviewer": "rev", "notes": "checked"})
    assert d.status_code == 200
    done = d.json()
    assert done["status"] == "completed" and done["human_decision"]["reviewer"] == "rev"
    assert done["risk_memo"]["recommended_action"] == "clear"
    assert client.get("/investigations", params={"pending": "true"}).json() == []


def test_decision_unknown_case_is_404(client):
    r = client.post("/investigations/nope/decision", json={"decision": "confirm", "reviewer": "r"})
    assert r.status_code == 404
    assert client.get("/investigations/nope").status_code == 404


def test_decision_on_finished_case_is_409(client):
    case_id = client.post("/investigations", json={"entity_name": "Zed Quux Gmbh"}).json()["case_id"]
    r = client.post(f"/investigations/{case_id}/decision", json={"decision": "confirm", "reviewer": "r"})
    assert r.status_code == 409


def test_second_decision_is_409(client):
    case_id = client.post("/investigations", json={"entity_name": "Acme Trading LLC"}).json()["case_id"]
    body = {"decision": "confirm", "reviewer": "r"}
    assert client.post(f"/investigations/{case_id}/decision", json=body).status_code == 200
    assert client.post(f"/investigations/{case_id}/decision", json=body).status_code == 409


@pytest.mark.parametrize("payload", [{}, {"entity_name": ""}, {"entity_name": "   "}])
def test_invalid_entity_is_422(client, payload):
    assert client.post("/investigations", json=payload).status_code == 422


def test_invalid_decision_is_422(client):
    r = client.post("/investigations/x/decision", json={"decision": "maybe", "reviewer": "r"})
    assert r.status_code == 422


def test_llm_backend_down_is_502(client, llm):
    llm.fail = True
    r = client.post("/investigations", json={"entity_name": "Zed Quux Gmbh"})
    assert r.status_code == 502 and "LLM backend" in r.json()["detail"]
    assert client.get("/investigations").json() == []  # nothing saved for a failed run


def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    assert client.get("/health").status_code == 200  # health stays open
    assert client.get("/investigations").status_code == 401
    assert client.get("/investigations", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/investigations", headers={"X-API-Key": "secret"}).status_code == 200


def test_health_503_when_store_unavailable(llm, tmp_path):
    bad = tmp_path / "is_a_dir"
    bad.mkdir()
    with TestClient(create_app(graph=build_graph(), db_path=bad)) as c:
        assert c.get("/health").status_code == 503


def test_missing_sanctions_data_is_503_not_500(client, monkeypatch):
    sanctions_lookup._load_list.cache_clear()
    monkeypatch.setitem(sanctions_lookup._SOURCE_FILES, "us_ofac_sdn", config.REPO_ROOT / "nope.csv")
    r = client.post("/investigations", json={"entity_name": "Zed Quux Gmbh"})
    assert r.status_code == 503 and "download_public_data.py" in r.json()["detail"]
