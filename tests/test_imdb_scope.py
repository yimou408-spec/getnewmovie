"""IMDb migration contracts; all review text and entities are synthetic."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.services.evidence import EvidenceService, configured_adapters
from app.services.opinions import OpinionPipeline, validate_synthesis
from app.services.storage import Repository
from scripts import backend_admin
from scripts.movie_server import create_app
from scripts.s0_contracts import Constraints, Evidence, ExternalMovieIdentity, Movie, SourceEvidenceResult
from tests.test_movie_intent import CatalogDouble


def identity(**changes):
    return ExternalMovieIdentity(**{**dict(provider="imdb", external_id="tt0000001",
        status="confirmed", basis="human_verified", url="https://www.imdb.com/title/tt0000001/"), **changes})


@pytest.mark.parametrize("provider,external_id,url", [
    ("imdb", "123", "https://www.imdb.com/title/123/"),
    ("imdb", "nm0000001", "https://www.imdb.com/title/nm0000001/"),
    ("imdb", "tt123", "https://www.imdb.com/title/tt123/"),
    ("tmdb", "tt0000001", "https://www.themoviedb.org/movie/tt0000001"),
    ("douban", "tt0000001", "https://movie.douban.com/subject/tt0000001/"),
    ("itunes", "tt0000001", "https://itunes.apple.com/us/movie/id1"),
    ("imdb", "tt0000001", "https://www.imdb.com/title/tt0000002/"),
    ("imdb", "tt0000001", "https://www.imdb.com/title/tt0000001/?key=x"),
])
def test_external_ids_are_provider_specific(provider, external_id, url):
    with pytest.raises(ValidationError):
        ExternalMovieIdentity(provider=provider, external_id=external_id, url=url,
                              status="confirmed", basis="human_verified")


def test_imdb_mapping_cli_roundtrip_preserves_catalog_identity(tmp_path, monkeypatch):
    path = tmp_path / "mappings.sqlite3"
    monkeypatch.setattr("sys.argv", ["backend_admin", "--database", str(path), "map",
        "--movie-id", "itunes:101", "--provider", "imdb", "--external-id", "tt0000001",
        "--basis", "human_verified", "--confirmed"])
    assert backend_admin.main() == 0
    repo = Repository(path)
    try:
        movie = Movie(movie_id="itunes:101", title="Invented movie")
        results = EvidenceService(repo).collect(movie)
        assert movie.movie_id == "itunes:101" and movie.title == "Invented movie"
        assert movie.external_ids == [identity()]
        assert [(r.source, r.status) for r in results] == [("IMDb", "not_configured")]
    finally:
        repo.close()


def test_default_api_has_imdb_pending_without_douban_or_false_capability(tmp_path, monkeypatch):
    monkeypatch.delenv("MOVIE_DOUBAN_LIVE", raising=False)
    assert "douban" not in configured_adapters(token="")
    assert "imdb" not in configured_adapters(token="")
    repo = Repository(tmp_path / "api.sqlite3")
    with TestClient(create_app(CatalogDouble(), evidence_service=EvidenceService(repo))) as client:
        data = client.post("/recommendations", json=dict(mode="discover", query="look", session_id="legacy")).json()
        assert data["status"] == "ready"
        assert {r["source"] for r in data["source_results"]} == {"IMDb"}
        assert all(r["status"] == "not_configured" and not r["evidence"] for r in data["source_results"])
        assert client.get("/health").json()["capabilities"]["reviews"] is False


def test_legacy_review_adapter_does_not_hide_pending_imdb():
    class LegacyReviews:
        source = "TMDB Reviews"
        identity_provider = "tmdb"

        def fetch(self, *args):
            pytest.fail("No confirmed mapping: no HTTP or adapter call is allowed")

    repo = Repository(":memory:")
    try:
        results = EvidenceService(repo, {"tmdb_reviews": LegacyReviews()}).collect(
            Movie(movie_id="itunes:101", title="Invented movie"))
        assert {(r.source, r.status) for r in results} == {
            ("IMDb", "not_configured"), ("TMDB Reviews", "not_configured")}
    finally:
        repo.close()


@pytest.mark.parametrize("key,provides_reviews", [("imdb", True), ("tmdb", False), ("tmdb_reviews", False)])
def test_health_uses_adapter_review_capability_instead_of_provider_name(key, provides_reviews):
    class Adapter:
        pass

    adapter = Adapter()
    adapter.provides_reviews = provides_reviews
    repo = Repository(":memory:")
    try:
        with TestClient(create_app(CatalogDouble(), evidence_service=EvidenceService(repo, {key: adapter}))) as client:
            assert client.get("/health").json()["capabilities"]["reviews"] is provides_reviews
    finally:
        repo.close()


def review(rid="rw0000001", *, claim="Synthetic: slow-paced, light-hearted.", author="Invented A"):
    return Evidence(evidence_id=rid, movie_id="itunes:101", source="IMDb",
        url=f"https://www.imdb.com/review/{rid}/", retrieved_at="2026-11-01T00:00:00Z",
        kind="review", granularity="excerpt", claim=claim, author=author,
        source_content_id=rid, usage_basis="synthetic", spoiler_level="safe")


def summarize(entries, **options):
    result = SourceEvidenceResult(movie_id="itunes:101", source="IMDb", status="ok", evidence=entries)
    return OpinionPipeline(**options).run("itunes:101", Constraints(moods=["轻松解压"]), [result])[0]


def test_imdb_reviews_compare_sample_without_claiming_independent_sources_or_second_source():
    entries = [review(), review("rw0000002", claim="Synthetic: fast-paced, light-hearted.", author="Invented B")]
    calls = []
    summary = summarize(entries, supplement=lambda mid: calls.append(mid))
    assert summary.status == "compared" and summary.comparison_scope == "single_platform"
    assert summary.independent_group_count == 0 and summary.synthetic is True
    assert {c.kind for c in summary.comparisons} == {"agreement", "disagreement"}
    assert all("IMDb" in c.text and "独立" not in c.text for c in summary.comparisons)
    assert summary.matches and summary.followup_status == "not_needed" and not calls
    assert any("单一平台" in line for line in summary.limitations)
    validate_synthesis(summary, "itunes:101", entries, Constraints(moods=["轻松解压"]))
    summary.comparison_scope = "independent_sources"
    with pytest.raises(ValueError):
        validate_synthesis(summary, "itunes:101", entries, Constraints(moods=["轻松解压"]))


def test_same_author_missing_review_id_and_copied_text_do_not_create_sample_agreement():
    a = review()
    b = review("rw0000002", claim="Synthetic: fast-paced.")
    assert not summarize([a, b]).comparisons
    b.author = "Invented B"
    b.source_content_id = None
    assert not summarize([a, b]).comparisons
    b.source_content_id = "rw0000002"
    b.claim = a.claim
    assert not summarize([a, b]).comparisons
    b.claim = "Synthetic: fast-paced."
    b.spoiler_level = "unknown"
    assert not summarize([a, b]).comparisons


@pytest.mark.parametrize("url", [
    "https://other.example/review/rw0000002/",
    "https://www.imdb.com/review/rw0000001/",
    "http://www.imdb.com/review/rw0000002/",
    "https://www.imdb.com/review/rw0000002/?tracking=x",
    "https://www.imdb.com/title/tt0000002/",
])
def test_imdb_opinions_require_canonical_review_url_bound_to_record_id(url):
    a = review()
    b = review("rw0000002", claim="Synthetic: fast-paced.", author="Invented B")
    b.url = url
    summary = summarize([a, b])
    assert not summary.comparisons
    assert all(p.evidence_id != b.evidence_id for p in summary.opinions)


def test_same_imdb_review_cannot_be_relabelled_as_two_records():
    a = review()
    b = review("rw0000002", claim="Synthetic: fast-paced.", author="Invented B")
    b.url = a.url
    b.source_content_id = a.source_content_id
    assert not summarize([a, b]).comparisons


def test_imdb_single_platform_fixture_is_executable_and_keeps_douban_optional():
    from pathlib import Path
    from scripts.s0_contracts import RecommendationResponse
    data = json.loads(Path("contracts/adapter-examples/imdb-review-excerpts.json").read_text(encoding="utf-8"))
    source = SourceEvidenceResult.model_validate(data)
    summary = summarize(source.evidence)
    assert summary.comparison_scope == "single_platform" and summary.status == "compared"
    wire = json.loads(Path("contracts/examples/success.json").read_text(encoding="utf-8"))
    mid = wire["candidates"][0]["movie"]["movie_id"]
    source.movie_id = mid
    for entry in source.evidence:
        entry.movie_id = mid
    summary = OpinionPipeline().run(mid, Constraints(), [source])[0]
    wire["evidence"].extend(e.model_dump(mode="json") for e in source.evidence)
    wire["source_results"] = [source.model_dump(mode="json")]
    wire["candidates"][0]["opinion_summary"] = summary.model_dump(mode="json")
    RecommendationResponse.model_validate(wire)
