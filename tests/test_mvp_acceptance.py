"""Exercise the acceptance workflow offline with explicit doubles."""
import httpx
import json

from app.services.storage import Repository
from scripts.mvp_acceptance import run_acceptance, main
from scripts.mvp_model import ModelSettings
from tests.test_mvp_workflow import Catalog


def test_live_acceptance_requires_opt_in_without_network(monkeypatch, capsys):
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    assert main([]) == 2
    assert 'NOT RUN' in capsys.readouterr().out


def test_live_acceptance_missing_config_never_calls_network(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr('scripts.mvp_model.ENV_FILE', tmp_path / 'absent.env')
    for key in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    assert main(['--live']) == 2
    assert 'NOT_CONFIGURED' in capsys.readouterr().out


def test_acceptance_runs_confirmation_memory_deletion_and_fault_recovery_offline():
    def handler(request):
        data = json.loads(request.content)
        user = json.loads(data['messages'][1]['content'])
        query = user['query']
        intent = {'action': 'recommend', 'updates': {'genres': ['喜剧'], 'max_runtime_minutes': 120},
                  'conflicts': ['synthetic pick conflict'], 'unhandled': []}
        if '90' in query or '100' in query:
            intent = {'action': 'refine', 'updates': {'max_runtime_minutes': 90 if '90' in query else 100}}
        return httpx.Response(200, json={'model': 'offline-double', 'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(intent)}}], 'usage': {'total_tokens': 1}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = ModelSettings('https://offline.example', 'OFFLINE_SECRET', 'offline-double')
    repo = Repository(':memory:')
    catalog = Catalog()
    catalog.fetch_count = 0
    report = run_acceptance(catalog, repo, settings, model_client=client, max_model_requests=4)
    assert report['passed'], report['checks']
    assert report['model_requests'] == 4
    assert report['fault_injection']['mode'] == 'offline_transport_timeout'
    assert report['checks']['real_refine_applies_seen_memory'] is True
    assert repo.connection.execute('SELECT count(*) FROM identities').fetchone()[0] == 0
    assert 'OFFLINE_SECRET' not in str(report)
