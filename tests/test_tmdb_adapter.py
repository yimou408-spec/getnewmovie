"""Offline TMDB metadata integration; all payloads below are invented fixtures."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.budget import RequestBudget, budget_scope
from app.services.evidence import EvidenceService, configured_adapters
from app.services.storage import Repository
from scripts.movie_catalog_errors import CatalogError
from scripts.movie_server import create_app
from scripts.s0_contracts import ExternalMovieIdentity, Movie
from scripts.tmdb_adapter import TMDBSource
from tests.test_movie_intent import CatalogDouble


def payload(**changes):
    return dict(id=129, title="离线动画", original_title="Offline animation",
                release_date="2001-07-20", runtime=125,
                alternative_titles={"titles": [{"iso_3166_1": "CN", "title": "离线别名"}]},
                **changes)


def mapped_movie():
    return Movie(movie_id="itunes:101", title="Apple offline title", year=2001,
                 runtime_minutes=124, external_ids=[ExternalMovieIdentity(
                     provider="tmdb", external_id="129", status="confirmed",
                     basis="human_verified", url="https://www.themoviedb.org/movie/129")])


def source(handler):
    return TMDBSource("SECRET", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_metadata_preserves_same_movie_binding_and_never_extracts_reviews_or_scores():
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url == "https://api.themoviedb.org/3/movie/129?language=zh-CN&append_to_response=alternative_titles"
        assert request.headers["authorization"] == "Bearer SECRET"
        return httpx.Response(200, json=payload(overview="Unsafe plot SECRET", vote_average=9.9))
    adapter = source(handle)
    with budget_scope(RequestBudget(max_http=1)) as budget:
        result = adapter.fetch("itunes:101", "129")
    assert result.status == "ok" and budget.http_calls == 1 and len(calls) == 1
    assert result.ratings == []
    evidence = result.evidence[0]
    assert evidence.movie_id == "itunes:101" and evidence.kind == "metadata"
    assert evidence.usage_basis == "provider_terms" and evidence.spoiler_level == "safe"
    assert "离线动画" in evidence.claim and "离线别名" in evidence.claim
    assert "125" in evidence.claim and str(evidence.url).endswith("/movie/129")
    assert "SECRET" not in result.model_dump_json() and "Unsafe plot" not in evidence.claim


@pytest.mark.parametrize("status,expected", [(401, "not_configured"), (403, "access_limited"),
    (404, "no_results"), (429, "access_limited"), (500, "upstream_error"), (302, "access_limited")])
def test_http_statuses_have_bounded_sanitized_results(status, expected):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="SECRET", headers={"location": "https://example.com/SECRET"})
    result = source(handle).fetch("itunes:101", "129")
    assert result.status == expected and len(calls) == 1
    assert result.evidence == [] and "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize("data", [[], {"id": 535075, "title": "Wrong film"},
    {"id": True, "title": "Invalid ID"}, {"id": 129},
    {"id": 129, "title": "Advertising 448832𝟵.com"},
    {"id": 129, "title": "<script>bad()</script>"}])
def test_wrong_movie_malformed_and_polluted_titles_are_not_published(data):
    result = source(lambda r: httpx.Response(200, json=data)).fetch("itunes:101", "129")
    assert result.status == "parse_error" and not result.evidence


def test_optional_fields_and_aliases_are_bounded_and_suspicious_aliases_omitted():
    data = {"id": 129, "title": "离线动画", "runtime": True, "release_date": "bad",
            "alternative_titles": {"titles": [{"title": "x" * 500}, {"title": "https://bad.example"},
                {"title": "离线动画"}, {"title": "离线别名"}]}}
    result = source(lambda r: httpx.Response(200, json=data)).fetch("itunes:101", "129")
    assert result.status == "ok"
    assert "时长：未知" in result.evidence[0].claim
    assert "https://bad" not in result.model_dump_json() and "x" * 500 not in result.model_dump_json()
    assert "离线别名" in result.evidence[0].claim


def test_network_errors_do_not_leak_and_budget_exhaustion_prevents_transport():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("SECRET", request=request)
    adapter = source(handle)
    with budget_scope(RequestBudget(max_http=1)) as budget:
        assert adapter.fetch("itunes:101", "129").status == "timeout"
        with pytest.raises(CatalogError):
            adapter.fetch("itunes:101", "129")
    assert budget.http_calls == 1 and len(calls) == 1
    with pytest.raises(ValueError):
        adapter.fetch("itunes:101", "129?secret=SECRET")
    assert len(calls) == 1


def test_confirmed_mapping_cache_and_stale_metadata_do_not_change_apple_facts(tmp_path):
    repo = Repository(tmp_path / "tmdb.sqlite3")
    movie = mapped_movie()
    repo.register_mapping(movie.movie_id, movie.external_ids[0])
    plain = movie.model_copy(update={"external_ids": None}, deep=True)
    now, calls = [100], []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload()) if len(calls) == 1 else httpx.Response(500)
    service = EvidenceService(repo, {"tmdb": source(handle)}, ttl=10, clock=lambda: now[0])
    first = next(r for r in service.collect(plain) if r.source == "TMDB")
    assert first.status == "ok" and plain.external_ids[0].external_id == "129"
    assert plain.title == movie.title and plain.runtime_minutes == 124
    cached = next(r for r in service.collect(plain) if r.source == "TMDB")
    assert cached.cache_status == "fresh" and len(calls) == 1
    now[0] = 111
    stale = next(r for r in service.collect(plain) if r.source == "TMDB")
    assert stale.status == "upstream_error" and stale.cache_status == "stale"
    assert stale.evidence[0].retrieved_at == first.evidence[0].retrieved_at


def test_missing_and_candidate_mapping_never_issue_search_or_details():
    adapter = source(lambda r: pytest.fail("No network without confirmed mapping"))
    service = EvidenceService(Repository(":memory:"), {"tmdb": adapter})
    plain = Movie(movie_id="itunes:101", title="Offline")
    assert next(r for r in service.collect(plain) if r.source == "TMDB").status == "not_configured"
    movie = mapped_movie()
    movie.external_ids[0].status, movie.external_ids[0].basis = "candidate", "title_year"
    assert next(r for r in service.collect(movie) if r.source == "TMDB").status == "ambiguous"


def test_recommendation_publishes_metadata_and_mapping_without_mutating_shared_catalog():
    repo = Repository(":memory:")
    repo.register_mapping("itunes:101", mapped_movie().external_ids[0])
    class SharedCatalog(CatalogDouble):
        def __init__(self):
            super().__init__()
            self.rows = super().pool([])
        def pool(self, genres):
            return self.rows
    catalog = SharedCatalog()
    service = EvidenceService(repo, {"tmdb": source(lambda r: httpx.Response(200, json=payload()))})
    client = TestClient(create_app(catalog, repository=repo, evidence_service=service))
    response = client.post("/recommendations", json=dict(mode="discover", query="look", session_id="legacy"))
    assert response.status_code == 200
    data = response.json()
    candidate = next(c for c in data["candidates"] if c["movie"]["movie_id"] == "itunes:101")
    assert candidate["movie"]["title"] == "Offline 喜剧" and candidate["movie"]["runtime_minutes"] == 90
    assert candidate["movie"]["external_ids"][0]["external_id"] == "129"
    assert any(e["source"] == "TMDB" for e in data["evidence"])
    assert response.headers["x-upstream-calls"] == "1"
    assert catalog.rows[0][0].external_ids is None
    assert client.get("/health").json()["capabilities"]["reviews"] is False
    assert "SECRET" not in json.dumps(data)


def test_only_explicitly_configured_token_enables_tmdb(monkeypatch):
    monkeypatch.delenv("MOVIE_DOUBAN_LIVE", raising=False)
    monkeypatch.delenv("TMDB_READ_TOKEN", raising=False)
    monkeypatch.delenv("MOVIE_TMDB_LIVE", raising=False)
    assert "tmdb" not in configured_adapters()
    monkeypatch.setenv("TMDB_READ_TOKEN", "SECRET")
    assert "tmdb" in configured_adapters()
    monkeypatch.setenv("MOVIE_TMDB_LIVE", "0")
    assert "tmdb" not in configured_adapters()


def test_disabled_adapter_reports_registered_mapping_without_network():
    repo = Repository(":memory:")
    repo.register_mapping("itunes:101", mapped_movie().external_ids[0])
    result = next(r for r in EvidenceService(repo).collect(
        Movie(movie_id="itunes:101", title="Offline")) if r.source == "TMDB")
    assert result.status == "not_configured" and not result.evidence
