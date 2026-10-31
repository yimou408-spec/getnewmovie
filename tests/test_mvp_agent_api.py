"""Product API integration: injected model/catalog, no network or real secrets."""
from fastapi.testclient import TestClient

from scripts.movie_server import create_app
from scripts.mvp_intent_contracts import IntentDecision
from tests.test_mvp_workflow import Catalog, Model


def setup():
    catalog = Catalog()
    catalog.fetch_count = 0
    model = Model(IntentDecision(updates={"genres": ["喜剧"], "max_runtime_minutes": 120}))
    client = TestClient(create_app(catalog, model_factory=lambda: model))
    sid = client.post("/sessions").json()["session_id"]
    return client, catalog, model, sid


def body(sid, query):
    return {"mode": "discover", "query": query, "session_id": sid, "input_source": "natural_language", "constraints": {}}


def test_product_api_uses_model_graph_and_preserves_followup_conditions():
    client, catalog, model, sid = setup()
    first = client.post("/recommendations", json=body(sid, "喜剧，120分钟以内"))
    assert first.status_code == 200
    assert first.json()["interpretation"]["method"] == "llm-v1"
    assert len(first.json()["candidates"]) == 3
    model.intent = IntentDecision(action="refine", updates={"max_runtime_minutes": 90})
    followup = body(sid, "改成90分钟以内")
    # The actual frontend serializes defaults as well as fresh picks.
    followup["constraints"] = {"genres": [], "moods": [], "max_runtime_minutes": None, "exclude_movie_ids": [], "era": "any"}
    second = client.post("/recommendations", json=followup).json()
    assert second["interpretation"]["effective_constraints"]["genres"] == ["喜剧"]
    assert all(c["movie"]["runtime_minutes"] <= 90 for c in second["candidates"])
    assert client.get("/health").json()["capabilities"]["model_understanding"] is True


def test_model_failure_returns_controlled_error_without_catalog_or_fake_results():
    client, catalog, model, sid = setup()
    model.status = "timeout"
    response = client.post("/recommendations", json=body(sid, "喜剧"))
    assert response.status_code == 504
    assert response.json()["code"] == "UPSTREAM_TIMEOUT"
    assert catalog.calls == 0


def test_api_confirmation_resumes_without_repeating_model_call():
    client, catalog, model, sid = setup()
    model.intent = IntentDecision(updates={"genres": ["喜剧"]}, unhandled=["豆瓣9分以上"])
    request = body(sid, "豆瓣9分以上的喜剧")
    pending = client.post("/recommendations", json=request).json()
    assert pending["status"] == "needs_clarification" and catalog.calls == 0
    question = pending["questions"][0]
    request["clarification"] = {"clarification_id": pending["clarification_id"],
        "answers": [{"question_id": question["question_id"], "option": question["options"][0]}]}
    result = client.post("/recommendations", json=request).json()
    assert result["status"] == "ready" and model.calls == 1
    assert any("未采用" in warning for warning in result["warnings"])
