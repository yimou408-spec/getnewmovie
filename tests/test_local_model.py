"""Local model support stays offline here; real inference is accepted separately."""
import json

import httpx
import pytest

from scripts.movie_config import Settings
from scripts.movie_model import ModelIntent


def test_loopback_model_needs_no_cloud_key_but_remote_http_is_invalid():
    local = Settings(llm_base_url='http://127.0.0.1:18181/v1', llm_model='local-qwen')
    assert local.report().llm.state == 'configured'
    assert local.report().llm.missing == []
    assert local.report().model_location == 'local'
    assert local.report().model_name == 'local-qwen'
    assert Settings(llm_base_url='http://model.example/v1', llm_model='model').report().llm.state == 'invalid'
    assert Settings(llm_base_url='https://model.example/v1', llm_model='model').report().llm.state == 'incomplete'


def test_local_mode_does_not_replace_a_selected_cloud_model(tmp_path):
    path = tmp_path / '.env'
    path.write_text('MOVIE_MODEL_BACKEND=local\n', encoding='utf-8')
    local = Settings.load(path, environ={})
    assert local.report().model_location == 'local'
    assert local.llm_model == 'qwen2.5-1.5b-instruct-q4_k_m'
    chosen = Settings.load(path, environ={'LLM_MODEL': 'deepseek-flash'})
    assert chosen.llm_model == 'deepseek-flash'
    assert chosen.report().llm.state == 'incomplete'


def test_local_request_has_constrained_json_and_records_only_successful_inference():
    settings = Settings(llm_base_url='http://127.0.0.1:18181/v1', llm_model='local-qwen')
    calls = []
    def handler(request):
        calls.append(request)
        assert 'Authorization' not in request.headers
        body = json.loads(request.content)
        assert body['response_format']['type'] == 'json_schema'
        assert body['temperature'] == 0
        return httpx.Response(200, json={'model': 'local-qwen', 'choices': [{'message': {
            'content': '{"constraints":{"max_runtime_minutes":100,"exclude_genres":["恐怖"]},"unhandled":[]}'}}]})
    parser = ModelIntent(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert parser.verification()['live_verified'] is False
    assert parser('一百分钟以内，不要恐怖')[0]['max_runtime_minutes'] == 100
    assert parser.verification()['live_verified'] is True
    assert parser.verification()['verified_at']
    assert '一百' not in json.dumps(parser.verification())
    parser('一百分钟以内，不要恐怖')
    assert len(calls) == 1


def test_failed_inference_does_not_claim_verified():
    settings = Settings(llm_base_url='http://127.0.0.1:18181/v1', llm_model='local-qwen')
    parser = ModelIntent(settings, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(Exception):
        parser('test')
    assert parser.verification()['live_verified'] is False


@pytest.mark.parametrize('query,fields,unsupported', [
    ('和家人看轻松的动画，90分钟以内', {'genres': ['动画'], 'moods': ['轻松解压'],
        'company': '和家人', 'max_runtime_minutes': 90, 'exclude_genres': ['恐怖']}, []),
    ('想看至少120分钟的电影', {'max_runtime_minutes': 120}, []),
    ('喜剧，100分钟以内', {'genres': ['喜剧']}, []),
    ('只看诺兰导演的电影', {}, []),
])
def test_local_semantic_errors_are_rejected_before_claiming_verified(query, fields, unsupported):
    from scripts.movie_catalog import CatalogError
    content = json.dumps({'constraints': fields, 'unhandled': unsupported})
    parser = ModelIntent(Settings(llm_base_url='http://127.0.0.1:18181/v1', llm_model='local'),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
            json={'choices': [{'message': {'content': content}}]}))))
    with pytest.raises(CatalogError):
        parser(query)
    assert not parser.verification()['live_verified']


def test_failed_model_cooldown_avoids_repeated_waits_and_can_recover():
    from scripts.movie_catalog import CatalogError
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(500) if len(calls) == 1 else httpx.Response(200, json={'choices': [
            {'message': {'content': '{"constraints":{},"unhandled":[]}'}}]})
    parser = ModelIntent(Settings(llm_base_url='http://127.0.0.1:18181/v1', llm_model='local'),
                         client=httpx.Client(transport=httpx.MockTransport(respond)))
    for text in ['first', 'second']:
        with pytest.raises(CatalogError):
            parser(text)
    assert len(calls) == 1
    parser.unavailable_until = 0
    assert parser('推荐一部电影') == ({}, [])
    assert parser.verification()['live_verified'] is True


def test_enabling_local_preserves_existing_cloud_selection(tmp_path, monkeypatch):
    from scripts import movie_local
    monkeypatch.setattr(movie_local, 'ROOT', tmp_path)
    path = tmp_path / '.env'
    original = 'LLM_MODEL=deepseek-flash\nLLM_API_KEY=private-test-key\n'
    path.write_text(original, encoding='utf-8')
    with pytest.raises(RuntimeError, match='preserved'):
        movie_local.enable_local_mode()
    assert path.read_text() == original
    path.write_text('LLM_MODEL=\n# Keep this comment\n', encoding='utf-8')
    movie_local.enable_local_mode()
    assert '# Keep this comment' in path.read_text()
    assert Settings.load(path, environ={}).is_local_model


@pytest.mark.parametrize('failure', ['download', 'startup'])
def test_local_bootstrap_failure_still_allows_the_frontend_to_start(monkeypatch, tmp_path, failure):
    from scripts import movie_demo, movie_local
    def broken():
        raise RuntimeError('deliberately unavailable')
    monkeypatch.setattr(movie_local, 'installed', lambda: failure != 'download')
    monkeypatch.setattr(movie_local, 'install', broken)
    class BrokenRuntime:
        def __enter__(self):
            broken()
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(movie_local, 'LocalRuntime', BrokenRuntime)
    settings = Settings.load(path=tmp_path / 'missing.env', environ={'MOVIE_MODEL_BACKEND': 'local'})
    with movie_demo.optional_local_runtime(settings):
        assert settings.llm_model == movie_local.LOCAL_MODEL


def test_installer_rejects_unverified_bytes_and_retains_completed_parts(tmp_path, monkeypatch):
    from scripts import movie_local
    monkeypatch.setattr(movie_local, 'HOME', tmp_path)
    real_client = httpx.Client
    def response(request):
        return httpx.Response(206, content=b'untrusted', headers={'content-range': 'bytes 0-8/9'})
    monkeypatch.setattr(movie_local.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(response)))
    target = tmp_path / 'model.gguf'
    with pytest.raises(RuntimeError, match='SHA256'):
        movie_local.download('https://example.com/model', target, 9, '0' * 64)
    assert not target.exists()
    assert (tmp_path / 'model.gguf.parts/0000').is_file()
