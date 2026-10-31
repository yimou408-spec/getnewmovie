"""Fault injection only. Fixtures are never installed as a movie fallback."""
import httpx
from fastapi.testclient import TestClient

from scripts.movie_catalog import AppleCatalog, CatalogError
from scripts.movie_config import Settings
from scripts.movie_server import create_app
from scripts.movie_tmdb import TMDBCatalog
from tests.test_movie_catalog import transport


def apple():
    return AppleCatalog(httpx.Client(transport=httpx.MockTransport(transport)), rate_limit=100)


def test_failed_tmdb_recovers_to_real_source_contract_without_changing_ids_or_clocks():
    calls = []
    def fail(request):
        calls.append(request)
        return httpx.Response(401)
    primary = TMDBCatalog('private-test-token', client=httpx.Client(transport=httpx.MockTransport(fail)))
    with TestClient(create_app(primary, backup_catalog=apple(), settings=Settings())) as client:
        request = dict(mode='discover', query='test', session_id='test', constraints={'genres': ['喜剧'], 'max_runtime_minutes': 100})
        first = client.post('/recommendations', json=request)
        assert first.status_code == 200, first.text
        data = first.json()
        assert data['status'] == 'ready'
        assert [c['movie']['movie_id'] for c in data['candidates']] == ['itunes:101']
        assert data['evidence'][0]['source'] == 'Apple iTunes US'
        assert data['candidates'][0]['movie']['ratings'] == []
        assert '已切换至 Apple' in ''.join(data['warnings'])
        assert 'private-test-token' not in first.text
        assert client.get('/movies/itunes:101').json()['title'] == 'Test Comedy'
        second = client.post('/recommendations', json=request).json()
        assert second['data_mode'] == 'cached' and second['evidence'] == data['evidence']
        assert len(calls) == 1  # Circuit cooldown avoids repeating a failing service.
        assert client.get('/health').json()['provider'] == 'Apple iTunes US'
        assert client.get('/health').json()['capabilities']['ratings'] is False
        assert client.get('/configuration').json()['catalog_fallback_active'] is True
        found = client.get('/movies', params={'query': 'off-chart search', 'year': 2020}).json()
        assert found['movies'][0]['movie_id'] == 'itunes:102'
        assert client.get('/movies', params={'query': 'off-chart search', 'year': 1990}).json()['movies'] == []


def test_valid_empty_tmdb_result_is_not_replaced_and_both_sources_failing_are_explicit():
    primary = TMDBCatalog('test', client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'results': []}))))
    backup = apple()
    with TestClient(create_app(primary, backup_catalog=backup, settings=Settings())) as client:
        body = dict(mode='discover', query='test', session_id='test')
        assert client.post('/recommendations', json=body).json()['status'] == 'empty'
        assert backup.fetch_count == 0
    primary = TMDBCatalog('test', client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    backup = AppleCatalog(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with TestClient(create_app(primary, backup_catalog=backup, settings=Settings())) as client:
        result = client.post('/recommendations', json=body)
        assert result.status_code == 503
        assert 'candidates' not in result.json()


def test_tmdb_recovers_after_cooldown_without_replacing_a_valid_empty_result(monkeypatch):
    from types import SimpleNamespace
    from scripts import movie_sources
    clock = [100.0]
    monkeypatch.setattr(movie_sources, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={'results': []})
    primary = TMDBCatalog('test', client=httpx.Client(transport=httpx.MockTransport(respond)))
    with TestClient(create_app(primary, backup_catalog=apple(), settings=Settings())) as client:
        body = dict(mode='discover', query='test', session_id='test')
        assert client.post('/recommendations', json=body).json()['status'] == 'ready'
        clock[0] += 61
        assert client.post('/recommendations', json=body).json()['status'] == 'empty'
        assert client.get('/configuration').json()['catalog_fallback_active'] is False
        assert client.get('/health').json()['provider'] == 'TMDB'


def test_model_failure_uses_labeled_rules_and_preserves_clarification_method():
    class FailedModel:
        method = 'llm-v1'
        def __call__(self, text):
            raise CatalogError()
    with TestClient(create_app(apple(), settings=Settings(), intent_parser=FailedModel())) as client:
        sid = client.post('/sessions').json()['session_id']
        body = dict(mode='discover', query='喜剧，100分钟以内，不要恐怖', session_id=sid, input_source='natural_language')
        result = client.post('/recommendations', json=body).json()
        assert result['status'] == 'ready'
        assert result['interpretation']['method'] == 'rules-v1'
        assert result['interpretation']['effective_constraints']['max_runtime_minutes'] == 100
        assert '模型暂时不可用' in ''.join(result['warnings'])
        body['query'] = '豆瓣8分以上的喜剧'
        pending = client.post('/recommendations', json=body).json()
        assert pending['status'] == 'needs_clarification'
        assert pending['evidence'] == [] and pending['interpretation']['method'] == 'rules-v1'
        done = client.post('/recommendations', json={**body, 'clarification': {
            'clarification_id': pending['clarification_id'], 'answers': [
                {'question_id': 'unhandled', 'option': '仅按已识别条件继续'}]}}).json()
        assert done['interpretation']['method'] == 'rules-v1'
        assert done['status'] == 'ready'
