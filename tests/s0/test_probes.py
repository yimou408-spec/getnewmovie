import json
from pathlib import Path

import httpx
import pytest

from scripts.s0_probe_tmdb import BudgetExceeded, TMDBProbe, summarize
from scripts.s0_probe_model import probe_model

ROOT = Path(__file__).resolve().parents[2]


def test_tmdb_budget_includes_failed_requests():
    def handle(request):
        assert request.headers["authorization"] == "Bearer SECRET"
        return httpx.Response(429, json={"status_message": "SECRET must not appear"})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        probe = TMDBProbe("SECRET", client=client, max_requests=1)
        assert probe.get("/search/movie", {"query": "test"})["error"] == "http_429"
        with pytest.raises(BudgetExceeded):
            probe.get("/search/movie", {"query": "test"})
        assert probe.calls == 1


def test_tmdb_missing_cn_is_unknown_and_runtime_is_not_zero():
    def handle(request):
        if request.url.path.endswith("/search/movie"):
            return httpx.Response(200, json={"results": [{"id": 42, "title": "测试片", "release_date": "2020-01-01"}]})
        return httpx.Response(200, json={
            "id": 42, "title": "测试片", "release_date": "2020-01-01", "runtime": None,
            "genres": [], "keywords": {"keywords": []}, "alternative_titles": {"titles": []},
            "watch/providers": {"results": {"US": {"link": "https://www.themoviedb.org/movie/42/watch"}}},
        })
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        probe = TMDBProbe("secret", client=client, max_requests=2)
        row = probe.inspect({"sample_id": "test", "query": "测试片", "year": 2020}, "CN")
    assert row["runtime_minutes"] is None
    assert row["availability_status"] == "unknown"
    assert row["identity_status"] == "candidate_unverified"
    assert row["manual_review_required"] is True
    assert summarize([row])["unknown_availability_count"] == 1


def test_tmdb_ambiguous_search_does_not_choose_first():
    def handle(request):
        return httpx.Response(200, json={"results": [{"id": 1}, {"id": 2}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        probe = TMDBProbe("secret", client=client, max_requests=2)
        result = probe.inspect({"sample_id": "test", "query": "同名片", "year": None}, "CN")
    assert result["identity_status"] == "ambiguous"
    assert probe.calls == 1


def test_tmdb_schema_change_and_connection_error_are_bounded():
    def handle(request):
        raise httpx.ConnectError("SECRET", request=request)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        probe = TMDBProbe("SECRET", client=client, max_requests=2)
        assert probe.get("/search/movie", {}) == {"error": "network_error"}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))) as client:
        probe = TMDBProbe("SECRET", client=client, max_requests=2)
        assert probe.get("/search/movie", {})["error"] == "invalid_schema"


def test_model_probe_uses_fixed_input_and_records_invalid_json_without_secret():
    def handle(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer SECRET"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json SECRET"}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = probe_model("https://model.example/v1", "SECRET", "test-model", client=client)
    assert result["status"] == "invalid_structured_output"
    assert "SECRET" not in json.dumps(result)


def test_model_probe_rejects_wrong_semantics_and_plain_http():
    with pytest.raises(ValueError):
        probe_model("http://remote.example/v1", "secret", "m")
    def handle(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"max_runtime_minutes":90,"exclude_genres":["恐怖"]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert probe_model("https://model.example/v1", "secret", "m", client=client)["status"] == "semantic_mismatch"


def test_evaluation_seed_split_and_synthetic_provenance():
    tasks = json.loads((ROOT / "data/s0/eval_tasks.json").read_text(encoding="utf-8"))
    assert len(tasks) == 30
    assert len({t["task_id"] for t in tasks}) == 30
    assert sum(t["split"] == "dev" for t in tasks) == 20
    assert sum(t["split"] == "holdout" for t in tasks) == 10
    assert all(t["provenance"] == "synthetic" for t in tasks)
