"""TMDB adapter fixtures are synthetic; never treated as live acceptance."""
import httpx
import pytest
from fastapi.testclient import TestClient

from scripts.movie_config import Settings
from scripts.movie_server import create_app
from scripts.movie_tmdb import TMDBCatalog


def source(request):
    assert request.url.host == 'api.themoviedb.org'
    assert request.headers['Authorization'] == 'Bearer test-token'
    if request.url.path.endswith('/popular') or request.url.path.endswith('/discover/movie') or request.url.path.endswith('/search/movie'):
        assert request.url.params['include_adult'] == 'false'
        return httpx.Response(200, json={'results': [{'id': 101}, {'id': 102}]})
    mid = int(request.url.path.split('/')[-1])
    return httpx.Response(200, json={'id': mid, 'title': f'测试影片{mid}', 'runtime': 95 if mid == 101 else 130,
        'release_date': '2020-01-01', 'genres': [{'id': 35, 'name': '喜剧'}], 'adult': False,
        'vote_average': 7.5, 'vote_count': 120, 'poster_path': '/fixture.jpg',
        'credits': {'crew': [{'job': 'Director', 'name': 'Test Director'}]}})


def test_tmdb_recommendations_have_separate_ids_ratings_evidence_and_original_clocks():
    provider = TMDBCatalog('test-token', client=httpx.Client(transport=httpx.MockTransport(source)))
    with TestClient(create_app(provider, settings=Settings())) as client:
        request = {'mode': 'discover', 'query': 'test', 'session_id': 'test',
                   'constraints': {'genres': ['喜剧'], 'max_runtime_minutes': 100}}
        response = client.post('/recommendations', json=request)
        assert response.status_code == 200, response.text
        data = response.json()
        assert [c['movie']['movie_id'] for c in data['candidates']] == ['tmdb:101']
        movie = data['candidates'][0]['movie']
        assert movie['ratings'][0]['source'] == 'TMDB' and movie['ratings'][0]['value'] == 7.5
        assert movie['director'] == 'Test Director'
        assert {e['kind'] for e in data['evidence']} == {'metadata', 'rating'}
        cached = client.post('/recommendations', json=request).json()
        assert cached['data_mode'] == 'cached' and cached['evidence'] == data['evidence']
        assert client.get('/movies/tmdb:101').status_code == 200
        assert client.get('/movies/syn:101').status_code == 404
        assert client.get('/health').json()['capabilities']['ratings'] is True


def test_tmdb_search_keeps_identity_confirmation_and_exact_year():
    provider = TMDBCatalog('test-token', client=httpx.Client(transport=httpx.MockTransport(source)))
    assert len(provider.search('测试', 2020)) == 2
    assert provider.search('测试', 1990) == []


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_both_sources_failing_remains_explicit_without_leaking_credentials(status):
    from scripts.movie_catalog import AppleCatalog
    provider = TMDBCatalog('test-token', client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status))))
    backup = AppleCatalog(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with TestClient(create_app(provider, settings=Settings(), backup_catalog=backup)) as client:
        response = client.post('/recommendations', json={'mode': 'discover', 'query': 'test', 'session_id': 'test'})
        assert response.status_code == 503
        assert 'candidates' not in response.json() and 'test-token' not in response.text


def test_missing_token_makes_no_network_request():
    def no_network(request):
        raise AssertionError('Network must not be used')
    provider = TMDBCatalog('', client=httpx.Client(transport=httpx.MockTransport(no_network)))
    from scripts.movie_catalog import CatalogError
    with pytest.raises(CatalogError) as error:
        provider.pool([])
    assert error.value.code == 'NOT_CONFIGURED'
