"""Synthetic API responses; no live review text or credentials in fixtures."""
import httpx
import pytest

from app.services.budget import RequestBudget, budget_scope
from app.services.evidence import EvidenceService, configured_adapters
from app.services.storage import Repository
from scripts.movie_catalog_errors import CatalogError
from scripts.tmdb_reviews import TMDBReviewSource
from tests.test_tmdb_adapter import mapped_movie


RID = "a" * 24


def payload(**changes):
    return {"id": 129, "page": 1, "total_results": 1, "results": [{
        "id": RID, "author": "Offline author", "content": "Invented opinion about the pacing.",
        "url": f"https://www.themoviedb.org/review/{RID}", **changes}]}


def source(data, code=200):
    return TMDBReviewSource("SECRET", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(code, json=data))))


def test_review_is_bound_attributed_bounded_and_never_claimed_safe_or_independent():
    calls = []
    def handle(request):
        calls.append(request)
        assert str(request.url).endswith('/129/reviews?language=en-US&page=1')
        return httpx.Response(200, json=payload(content="Invented opinion. " * 100))
    adapter = TMDBReviewSource("SECRET", client=httpx.Client(transport=httpx.MockTransport(handle)))
    with budget_scope(RequestBudget(max_http=1)) as budget:
        result = adapter.fetch("itunes:101", "129")
        with pytest.raises(CatalogError):
            adapter.fetch("itunes:101", "129")
    assert budget.http_calls == len(calls) == 1
    entry = result.evidence[0]
    assert entry.movie_id == "itunes:101" and entry.source == "TMDB Reviews"
    assert entry.author == "Offline author" and entry.source_content_id == RID
    assert entry.kind == "review" and entry.granularity == "excerpt"
    assert entry.spoiler_level == "unknown" and entry.independent_source_group is None
    assert entry.usage_basis == "provider_terms" and len(entry.claim) <= 600
    assert not result.ratings and "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize('data', [[], {}, {"id": 130, "results": []},
    {"id": 129, "results": {}}, {"id": True, "results": []}])
def test_wrong_movie_and_malformed_payload_are_rejected(data):
    assert source(data).fetch("itunes:101", "129").status == "parse_error"


@pytest.mark.parametrize('changes', [{"url": "https://evil.example/review/" + RID},
    {"id": "invalid"}, {"content": "<script>bad</script>"}, {"content": "See https://example.org"},
    {"author": ""}, {"content": ""}])
def test_invalid_attribution_links_and_active_content_never_publish(changes):
    result = source(payload(**changes)).fetch("itunes:101", "129")
    assert result.status == "parse_error" and not result.evidence


def test_empty_coverage_is_no_results_and_duplicate_reviews_do_not_inflate_count():
    assert source({"id": 129, "results": []}).fetch("itunes:101", "129").status == "no_results"
    data = payload()
    data['results'] *= 10
    assert len(source(data).fetch("itunes:101", "129").evidence) == 1


@pytest.mark.parametrize('code,status', [(401,'not_configured'),(403,'access_limited'),
    (429,'access_limited'),(302,'access_limited'),(404,'no_results'),(500,'upstream_error')])
def test_http_errors_are_sanitized(code, status):
    result = source({"SECRET": "SECRET"}, code).fetch("itunes:101", "129")
    assert result.status == status and 'SECRET' not in result.model_dump_json()


def test_missing_token_invalid_id_json_and_network_failures_do_not_publish():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout('SECRET', request=request)
    client = httpx.Client(transport=httpx.MockTransport(handle))
    assert TMDBReviewSource('', client=client).fetch('itunes:101', '129').status == 'not_configured'
    with pytest.raises(ValueError):
        TMDBReviewSource('SECRET', client=client).fetch('itunes:101', '129?bad')
    assert not calls
    result = TMDBReviewSource('SECRET', client=client).fetch('itunes:101', '129')
    assert result.status == 'timeout' and 'SECRET' not in result.model_dump_json()
    invalid = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='SECRET')))
    assert TMDBReviewSource('SECRET', client=invalid).fetch('itunes:101', '129').status == 'parse_error'


def test_review_adapter_reuses_confirmed_tmdb_mapping_with_separate_cache(tmp_path):
    repo = Repository(tmp_path / 'reviews.sqlite3')
    movie = mapped_movie()
    repo.register_mapping(movie.movie_id, movie.external_ids[0])
    service = EvidenceService(repo, {"tmdb_reviews": source(payload())})
    first = next(r for r in service.collect(movie) if r.source == "TMDB Reviews")
    second = next(r for r in service.collect(movie) if r.source == "TMDB Reviews")
    assert first.status == 'ok' and second.cache_status == 'fresh'
    assert repo.cache_get(movie.movie_id, 'TMDB', '129') is None
    assert second.evidence == first.evidence


def test_reviews_require_explicit_opt_in(monkeypatch):
    monkeypatch.setenv('TMDB_READ_TOKEN', 'SECRET')
    monkeypatch.setenv('MOVIE_TMDB_LIVE', '1')
    monkeypatch.delenv('MOVIE_TMDB_REVIEWS_LIVE', raising=False)
    assert 'tmdb_reviews' not in configured_adapters()
    monkeypatch.setenv('MOVIE_TMDB_REVIEWS_LIVE', '1')
    assert 'tmdb_reviews' in configured_adapters()
    monkeypatch.setenv('MOVIE_TMDB_LIVE', '0')
    assert 'tmdb_reviews' not in configured_adapters()


def test_recommendation_reviews_keep_attribution_and_never_enter_default_reasons():
    from fastapi.testclient import TestClient
    from scripts.movie_server import create_app
    from tests.test_movie_intent import CatalogDouble
    repo = Repository(':memory:')
    repo.register_mapping('itunes:101', mapped_movie().external_ids[0])
    client = TestClient(create_app(CatalogDouble(), repository=repo,
        evidence_service=EvidenceService(repo, {'tmdb_reviews': source(payload())})))
    response = client.post('/recommendations', json=dict(mode='discover', query='offline', session_id='legacy'))
    assert response.status_code == 200
    data = response.json()
    entry = next(e for e in data['evidence'] if e['kind'] == 'review')
    assert entry['author'] == 'Offline author' and entry['spoiler_level'] == 'unknown'
    assert all(entry['evidence_id'] not in c['reason']['evidence_ids'] for c in data['candidates'])
    assert client.get('/health').json()['capabilities']['reviews'] is True
