"""Offline configuration, model and demo-host regression checks; no real keys."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts.movie_config import Settings
from scripts.movie_model import ModelIntent
from scripts.movie_server import create_app


def test_dotenv_is_rooted_environment_wins_and_secrets_are_never_reported(tmp_path):
    path = tmp_path / '.env'
    path.write_text('LLM_BASE_URL=https://model.example/v1\nLLM_MODEL=test-model\n'
                    'LLM_API_KEY="test-secret-${UNEXPANDED}"\nTMDB_READ_TOKEN=test-token\n', encoding='utf-8')
    settings = Settings.load(path=path, environ={'LLM_API_KEY': 'override-secret'})
    assert settings.llm_api_key == 'override-secret'
    assert settings.tmdb_read_token == 'test-token'
    assert settings.provider == 'tmdb'
    report = json.dumps(settings.report().model_dump()) + repr(settings)
    assert 'override-secret' not in report and 'test-token' not in report
    assert settings.report().llm.state == 'configured'
    assert settings.report().llm.live_verified is False
    assert Settings.load(path=path, environ={}).llm_api_key == 'test-secret-${UNEXPANDED}'


def test_missing_partial_and_invalid_config_are_distinct(tmp_path):
    assert Settings.load(path=tmp_path/'missing', environ={}).provider == 'apple'
    partial = Settings.load(path=tmp_path/'missing', environ={'LLM_MODEL': 'test'})
    assert partial.report().llm.state == 'incomplete'
    invalid = Settings(llm_base_url='https://user:password@example.com/v1', llm_api_key='secret', llm_model='test')
    assert invalid.report().llm.state == 'invalid'
    assert 'password' not in invalid.report().model_dump_json()


def test_configuration_endpoint_is_read_only_redacted_and_served_under_api():
    settings = Settings(tmdb_read_token='private-test-token', catalog_provider='apple')
    with TestClient(create_app(settings=settings)) as client:
        root = client.get('/configuration')
        assert root.status_code == 200
        assert client.get('/api/configuration').json() == root.json()
        assert 'private-test-token' not in root.text
        assert root.json()['catalog_provider'] == 'apple'


def test_built_app_deep_links_and_unknown_api_do_not_return_html(tmp_path):
    (tmp_path/'index.html').write_text('<html>test app</html>', encoding='utf-8')
    with TestClient(create_app(settings=Settings(), frontend_dir=tmp_path)) as client:
        assert 'test app' in client.get('/watchlist').text
        assert 'test app' in client.get('/unknown').text
        assert 'test app' in client.get('/unknown/nested').text
        assert client.get('/api/health').json()['service'] == 'real-catalog'
        assert client.get('/api').status_code == 404
        assert client.get('/api/missing').status_code == 404
        assert client.get('/.env').status_code == 404
        assert client.get('/assets/missing.js').status_code == 404
        assert client.get('/assets/missing').status_code == 404


def test_model_intent_uses_one_bounded_authenticated_request_and_validates_output():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url == 'https://model.example/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-secret'
        body = json.loads(request.content)
        assert body['model'] == 'chosen-model' and body['max_tokens'] <= 512
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'constraints': {'max_runtime_minutes': 100, 'exclude_genres': ['恐怖']}, 'unhandled': []})}}]})
    settings = Settings(llm_base_url='https://model.example/v1', llm_api_key='test-secret', llm_model='chosen-model')
    parser = ModelIntent(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    parsed, unhandled = parser('100分钟以内，不要恐怖')
    assert parsed == {'max_runtime_minutes': 100, 'exclude_genres': ['恐怖']}
    assert not unhandled and len(calls) == 1


@pytest.mark.parametrize('content', ['not json', '{"constraints":{"movie_id":"tmdb:1"},"unhandled":[]}',
                                    '{"constraints":{"max_runtime_minutes":900},"unhandled":[]}',
                                    '{"constraints":{"max_runtime_minutes":true},"unhandled":[]}'])
def test_model_rejects_unusable_output_without_leaking_body_or_retry(content):
    settings = Settings(llm_base_url='https://model.example/v1', llm_api_key='test-secret', llm_model='test')
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    parser = ModelIntent(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    from scripts.movie_catalog import CatalogError
    with pytest.raises(CatalogError) as error:
        parser('test')
    assert 'test-secret' not in str(error.value.message) and content not in error.value.message
    assert len(calls) == 1


def test_configured_model_drives_session_clarification_before_any_catalog_request():
    from scripts.movie_tmdb import TMDBCatalog
    catalog_calls, model_calls = [], []
    def movie_source(request):
        catalog_calls.append(request)
        return httpx.Response(200, json={'results': []})
    def model_source(request):
        model_calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'constraints': {'genres': ['剧情']}, 'unhandled': ['指定演员暂不支持']})}}]})
    settings = Settings(llm_base_url='https://model.example/v1', llm_api_key='test-secret', llm_model='test')
    parser = ModelIntent(settings, client=httpx.Client(transport=httpx.MockTransport(model_source)))
    catalog = TMDBCatalog('test-token', client=httpx.Client(transport=httpx.MockTransport(movie_source)))
    with TestClient(create_app(catalog, settings=settings, intent_parser=parser)) as client:
        sid = client.post('/sessions').json()['session_id']
        body = dict(mode='discover', query='一段由模型解析的描述', session_id=sid,
                    input_source='natural_language', constraints={'genres': ['喜剧']})
        pending = client.post('/recommendations', json=body).json()
        assert pending['status'] == 'needs_clarification'
        assert pending['interpretation']['method'] == 'llm-v1'
        assert len(pending['questions']) == 2 and not catalog_calls
        response = client.post('/recommendations', json={**body, 'clarification': {
            'clarification_id': pending['clarification_id'], 'answers': [
                {'question_id': 'conflict', 'option': '按文字条件'},
                {'question_id': 'unhandled', 'option': '仅按已识别条件继续'}]}})
        assert response.status_code == 200
        assert response.json()['interpretation']['effective_constraints']['genres'] == ['剧情']
        assert len(model_calls) == 1 and len(catalog_calls) == 1
        # Structured interaction bypasses the configured model entirely.
        structured = client.post('/recommendations', json={**body, 'input_source': 'structured'})
        assert structured.status_code == 200
        assert len(model_calls) == 1
