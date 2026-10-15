"""Executable S0 expectations; written before the contract implementation."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.s0_contracts import RecommendationRequest, RecommendationResponse
from scripts.s0_mock_server import app

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return json.loads((ROOT / "contracts/examples" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", ["success", "empty", "clarification", "degraded"])
def test_shared_responses_conform(scenario):
    RecommendationResponse.model_validate(load(scenario))


def test_rejects_four_cards_and_unbound_evidence():
    data = load("success")
    data["candidates"] *= 4
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
    data = load("success")
    data["candidates"][0]["reason"]["evidence_ids"] = ["not-provided"]
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_rejects_duplicate_identity_and_wrong_film_reference():
    data = load("success")
    data["candidates"].append(copy.deepcopy(data["candidates"][0]))
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
    data = load("success")
    data["evidence"][0]["movie_id"] = "syn:other"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_empty_and_clarification_are_real_states():
    data = load("empty")
    data["candidates"] = load("success")["candidates"]
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
    data = load("clarification")
    data["questions"] = []
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_request_does_not_trust_user_id_or_allow_unbounded_questions():
    data = load("request")
    data["user_id"] = "someone-else"
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(data)
    data = load("request")
    data["clarification_count"] = 3
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(data)
    data = load("request")
    data["mode"] = "watchlist"
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(data)


def test_dangerous_link_and_rating_out_of_scale_are_rejected():
    data = load("success")
    data["evidence"][0]["url"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_rating_source_and_spoiler_flag_cannot_be_changed_silently():
    data = load("success")
    data["candidates"][0]["movie"]["ratings"][0]["source"] = "豆瓣"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
    data = load("success")
    data["evidence"][0]["spoiler_level"] = "contains_spoilers"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
    data = load("success")
    data["candidates"][0]["movie"]["ratings"][0]["value"] = 11
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


@pytest.mark.parametrize("scenario,status", [
    ("success", 200), ("empty", 200), ("clarification", 200),
    ("degraded", 200), ("timeout", 504), ("unconfigured", 503),
])
def test_mock_http_states(scenario, status):
    with TestClient(app) as client:
        response = client.post("/recommendations", json=load("request"), headers={"X-Mock-Scenario": scenario})
    assert response.status_code == status
    assert response.headers["X-Data-Mode"] == "synthetic"
    assert response.json()["data_mode"] == "synthetic"


def test_mock_lookup_disambiguates_by_year_and_exposes_openapi():
    with TestClient(app) as client:
        results = client.get("/movies", params={"query": "春日来信"}).json()["movies"]
        assert len(results) == 2
        assert len({item["movie_id"] for item in results}) == 2
        results = client.get("/movies", params={"query": "春日来信", "year": 2024}).json()["movies"]
        assert len(results) == 1
        assert results[0]["year"] == 2024
        assert client.get("/movies/syn:does-not-exist").status_code == 404
        assert "/recommendations" in client.get("/openapi.json").json()["paths"]


def test_mock_is_explicit_and_does_not_claim_real_memory():
    with TestClient(app) as client:
        result = client.post("/recommendations", json=load("request"), headers={"X-Mock-Scenario": "invalid"})
        assert result.status_code == 400
        assert client.post("/feedback", json={}).status_code == 404


def test_prototype_and_comparison_are_available_without_a_model():
    with TestClient(app) as client:
        assert "S0" in client.get("/").text
        result = client.post("/comparisons", json={"movie_ids": ["syn:letter-2024", "syn:orbit"]})
        assert result.status_code == 200
        assert len(result.json()["movies"]) == 2
        assert client.post("/comparisons", json={"movie_ids": ["syn:orbit", "syn:orbit"]}).status_code == 422
        assert client.post("/comparisons", json={"movie_ids": ["syn:orbit", "syn:missing"]}).status_code == 404
