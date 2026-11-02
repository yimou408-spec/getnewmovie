"""Evidence caching and shared request limits, with synthetic adapter results."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.budget import RequestBudget, budget_scope
from app.services.evidence import EvidenceService
from app.services.storage import Repository
from scripts.movie_catalog import AppleCatalog, CatalogError
from scripts.movie_server import create_app
from scripts.s0_contracts import Evidence, ExternalMovieIdentity, Movie, SourceEvidenceResult
from tests.test_movie_intent import CatalogDouble


def film():
    return Movie(movie_id="itunes:101", title="Offline film", external_ids=[ExternalMovieIdentity(
        provider="douban", external_id="123", status="confirmed", basis="human_verified",
        url="https://movie.douban.com/subject/123/")])


class Adapter:
    source = "Douban"
    def __init__(self):
        self.calls, self.fail = 0, False
    def fetch(self, movie_id, external_id):
        self.calls += 1
        if self.fail:
            return SourceEvidenceResult(movie_id=movie_id, source=self.source, status="timeout")
        return SourceEvidenceResult(movie_id=movie_id, source=self.source, status="ok", evidence=[Evidence(
            evidence_id="review-1", movie_id=movie_id, source=self.source, url="https://movie.douban.com/subject/123/",
            retrieved_at="2026-10-31T00:00:00Z", kind="review", granularity="excerpt", claim="Invented review",
            spoiler_level="unknown", usage_basis="synthetic", independent_source_group="publisher-1")])


def test_confirmed_mapping_required_and_unconfigured_source_never_calls(tmp_path):
    adapter = Adapter()
    service = EvidenceService(Repository(tmp_path / "e.sqlite3"), {"douban": adapter})
    plain = Movie(movie_id="itunes:101", title="Offline")
    assert service.collect(plain)[0].status == "not_configured"
    assert adapter.calls == 0
    candidate = film()
    candidate.external_ids[0].status = "candidate"
    candidate.external_ids[0].basis = "title_year"
    assert service.collect(candidate)[0].status == "ambiguous"
    assert adapter.calls == 0


def test_cache_hit_expiry_failure_stale_and_restart(tmp_path):
    now = [100]
    path = tmp_path / "e.sqlite3"
    repo, adapter = Repository(path), Adapter()
    service = EvidenceService(repo, {"douban": adapter}, clock=lambda: now[0], ttl=10)
    first = service.collect(film())[0]
    assert first.cache_status == "none"
    assert service.collect(film())[0].cache_status == "fresh" and adapter.calls == 1
    now[0] = 111
    adapter.fail = True
    expired = service.collect(film())[0]
    assert expired.status == "timeout" and expired.cache_status == "stale"
    assert expired.evidence[0].retrieved_at == first.evidence[0].retrieved_at
    reopened = EvidenceService(Repository(path), {"douban": adapter}, clock=lambda: 105, ttl=10)
    assert reopened.collect(film())[0].cache_status == "fresh"


def test_budget_counts_failed_http_calls_and_blocks_following_requests():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r), httpx.Response(500))[1]))
    catalog = AppleCatalog(client)
    budget = RequestBudget(max_http=1, max_search=1, seconds=1)
    with budget_scope(budget):
        with pytest.raises(CatalogError):
            catalog.get("/lookup", {"id": "1"})
        with pytest.raises(CatalogError) as error:
            catalog.get("/lookup", {"id": "2"})
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert budget.http_calls == 1 and len(calls) == 1


def test_deadline_and_search_budget_stop_before_transport():
    now = [0]
    budget = RequestBudget(max_http=10, max_search=1, seconds=1, clock=lambda: now[0])
    budget.consume(search=True)
    with pytest.raises(CatalogError):
        budget.consume(search=True)
    now[0] = 2
    with pytest.raises(CatalogError) as error:
        budget.check()
    assert error.value.code == "UPSTREAM_TIMEOUT"


def test_evidence_failure_does_not_erase_catalog_or_claim_reviews_available(tmp_path):
    service = EvidenceService(Repository(tmp_path / "e.sqlite3"), {})
    client = TestClient(create_app(CatalogDouble(), evidence_service=service))
    result = client.post("/recommendations", json=dict(mode="discover", query="look", session_id="legacy")).json()
    assert result["status"] == "ready" and len(result["candidates"]) == 3
    assert result["source_results"][0]["status"] == "not_configured"
    assert client.get("/health").json()["capabilities"]["reviews"] is False
    response = client.get("/health")
    assert response.headers["x-trace-id"]
    assert "authorization" not in response.headers


def test_mapping_registration_conflict_and_stale_ratings_never_become_current(tmp_path):
    repo = Repository(tmp_path / "mapping.sqlite3")
    movie = film()
    repo.register_mapping(movie.movie_id, movie.external_ids[0])
    assert repo.mappings(movie.movie_id) == movie.external_ids
    with pytest.raises(ValueError):
        repo.register_mapping("itunes:102", movie.external_ids[0])
    with pytest.raises(ValueError):
        repo.register_mapping(movie.movie_id, ExternalMovieIdentity(provider="douban", external_id="124", status="confirmed", basis="human_verified", url="https://movie.douban.com/subject/124/"))


def test_budget_lock_wait_is_bounded_and_released():
    from threading import RLock
    from app.services.budget import catalog_lock
    lock = RLock()
    with budget_scope(RequestBudget(seconds=.001, clock=lambda: 0)):
        with catalog_lock(lock):
            assert lock._is_owned()
    assert not lock._is_owned()


def test_unverified_material_not_persisted_or_published(tmp_path):
    class Unverified(Adapter):
        def fetch(self, movie_id, external_id):
            result = super().fetch(movie_id, external_id)
            result.evidence[0].usage_basis = "unverified"
            return result
    repo = Repository(tmp_path / "uncleared.sqlite3")
    result = EvidenceService(repo, {"douban": Unverified()}).collect(film())[0]
    assert result.evidence == []
    assert "Invented review" not in str(repo.cache_get("itunes:101", "Douban", "123"))


def test_request_deadline_returns_504_and_never_promotes_late_results():
    import time
    class SlowCatalog(CatalogDouble):
        def pool(self, genres):
            time.sleep(.15)
            return super().pool(genres)
    client = TestClient(create_app(SlowCatalog(), budget_factory=lambda: RequestBudget(seconds=.02)))
    started = time.monotonic()
    response = client.post("/recommendations", json=dict(mode="discover", query="look", session_id="legacy"))
    assert response.status_code == 504
    assert response.json()["code"] == "UPSTREAM_TIMEOUT"
    assert time.monotonic() - started < .12


def test_ratings_do_not_mutate_shared_catalog_or_leak_to_later_responses():
    from scripts.s0_contracts import Rating
    class SharedCatalog(CatalogDouble):
        def __init__(self):
            super().__init__()
            self.rows = super().pool([])
        def pool(self, genres):
            return self.rows
    catalog = SharedCatalog()
    class RatedEvidence:
        enabled = True
        def collect(self, movie):
            if not self.enabled:
                return []
            eid = "offline-rating-" + movie.movie_id
            return [SourceEvidenceResult(movie_id=movie.movie_id, source="Offline publisher", status="ok",
                evidence=[Evidence(evidence_id=eid, movie_id=movie.movie_id, source="Offline publisher",
                    url="https://example.com/rating", retrieved_at="2026-10-31T00:00:00Z", kind="rating",
                    claim="Synthetic rating for isolated test", spoiler_level="safe", usage_basis="synthetic")],
                ratings=[Rating(source="Offline publisher", value=4, scale=5, evidence_id=eid)])]
    evidence = RatedEvidence()
    client = TestClient(create_app(catalog, evidence_service=evidence))
    body = dict(mode="discover", query="look", session_id="legacy")
    first = client.post("/recommendations", json=body)
    assert first.status_code == 200
    assert all(len(c["movie"]["ratings"]) == 1 for c in first.json()["candidates"])
    evidence.enabled = False
    second = client.post("/recommendations", json=body)
    assert second.status_code == 200
    assert all(c["movie"]["ratings"] == [] for c in second.json()["candidates"])


def test_optional_evidence_deadline_preserves_candidates_and_does_not_cache_late_results(tmp_path):
    now, calls, limits = [0], [], []

    class SlowEvidence:
        source = "Douban"

        def fetch(self, mid, external_id):
            from app.services.budget import consume
            calls.append(mid)
            limits.append(consume(timeout=8))
            now[0] += 15
            return SourceEvidenceResult(movie_id=mid, source=self.source, status="no_results")

    catalog = CatalogDouble()
    repo = Repository(tmp_path / "optional.sqlite3")
    for movie, _ in catalog.pool([]):
        repo.register_mapping(movie.movie_id, ExternalMovieIdentity(provider="douban",
            external_id=movie.movie_id.split(":")[1], status="confirmed", basis="human_verified",
            url=f"https://movie.douban.com/subject/{movie.movie_id.split(':')[1]}/"))
    service = EvidenceService(repo, {"douban": SlowEvidence()})
    budget = RequestBudget(clock=lambda: now[0], seconds=45)
    with TestClient(create_app(catalog, repository=repo, evidence_service=service,
                              budget_factory=lambda: budget)) as client:
        response = client.post("/recommendations", json=dict(mode="discover", query="look", session_id="legacy"))
    assert response.status_code == 200
    assert len(response.json()["candidates"]) == 3
    records = [r for r in response.json()["source_results"] if r["source"] == "Douban"]
    assert len(records) == 3 and all(r["status"] == "timeout" for r in records)
    assert len(calls) == budget.http_calls == 1 and limits == [8]
    assert repo.connection.execute("SELECT count(*) FROM evidence_cache").fetchone()[0] == 0
    repo.close()


def test_optional_budget_shares_parent_counters_and_does_not_extend_total_deadline():
    from app.services.budget import optional_budget_scope
    now = [0]
    parent = RequestBudget(clock=lambda: now[0], seconds=6, max_http=2)
    with budget_scope(parent):
        with optional_budget_scope(seconds=12, reserve=1) as child:
            assert child.consume(timeout=8) == 5
            now[0] = 5
            with pytest.raises(CatalogError):
                child.consume()
        assert parent.http_calls == 1 and parent.check() == 1


def test_optional_timeout_returns_stale_cache_without_promoting_old_evidence(tmp_path):
    from app.services.budget import optional_budget_scope
    now = [0]
    repo, adapter = Repository(tmp_path / "stale.sqlite3"), Adapter()
    service = EvidenceService(repo, {"douban": adapter}, clock=lambda: now[0], ttl=10)
    first = next(r for r in service.collect(film()) if r.source == "Douban")
    now[0] = 20
    parent = RequestBudget(clock=lambda: now[0])
    with budget_scope(parent):
        with optional_budget_scope(seconds=0):
            stale = next(r for r in service.collect(film()) if r.source == "Douban")
    assert stale.status == "timeout" and stale.cache_status == "stale" and not stale.ratings
    assert stale.evidence == first.evidence and adapter.calls == 1
    assert repo.cache_get("itunes:101", "Douban", "123")[0] == 0
    repo.close()
