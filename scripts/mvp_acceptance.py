"""Opt-in bounded real model + Apple + temporary-memory acceptance.

Reports checks and sanitized model usage, never tokens or model response text.
The failure case injects a local timeout and is labelled separately from live.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

import httpx
from fastapi.testclient import TestClient

from app.services.evidence import EvidenceService
from app.services.storage import Repository
from scripts.movie_catalog import AppleCatalog
from scripts.movie_server import create_app
from scripts.mvp_model import ModelAdapter, ModelSettings
from scripts.s0_contracts import RecommendationResponse

ROOT = Path(__file__).resolve().parents[1]


def run_acceptance(catalog, repo, settings, *, model_client=None, max_model_requests=4):
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": {},
              "model_requests": 0, "models": [], "responses": [],
              "fault_injection": {"mode": "offline_transport_timeout"}}
    checks, fault = report["checks"], [False]
    def timeout(request):
        raise httpx.ReadTimeout("local acceptance injection", request=request)
    fault_client = httpx.Client(transport=httpx.MockTransport(timeout))
    class RecordedModel:
        def interpret(self, *args, **kwargs):
            if not fault[0] and report["model_requests"] >= max_model_requests:
                raise ValueError("acceptance model budget exhausted")
            adapter = ModelAdapter(settings, client=fault_client if fault[0] else model_client, max_requests=1)
            result = adapter.interpret(*args, **kwargs)
            if fault[0]:
                report["fault_injection"]["adapter_status"] = result.status
            else:
                report["model_requests"] += adapter.requests_made
                report["models"].append({"status": result.status, **result.metadata})
            return result
    app = create_app(catalog, repository=repo, model_factory=RecordedModel,
                     evidence_service=EvidenceService(repo))
    headers = None
    try:
        with TestClient(app) as client:
            token = client.post('/identities').json()['identity_token']
            headers = {"Authorization": "Bearer " + token}
            def session():
                return client.post('/sessions', headers=headers).json()['session_id']
            def post(label, body):
                response = client.post('/recommendations', headers=headers, json=body)
                data = response.json()
                if response.status_code == 200:
                    RecommendationResponse.model_validate(data)
                report['responses'].append({'case': label, 'http_status': response.status_code,
                    'status': data.get('status'), 'error_code': data.get('code'),
                    'candidate_ids': [c['movie']['movie_id'] for c in data.get('candidates', [])],
                    'effective_constraints': data.get('interpretation', {}).get('effective_constraints'),
                    'upstream_calls': int(response.headers.get('x-upstream-calls', 0)),
                    'memory_used': data.get('memory_used')})
                return response, data
            def valid(data, minutes):
                return data.get('status') in {'ready', 'empty'} and all(
                    c['movie']['movie_id'].startswith('itunes:') and '喜剧' in c['movie']['genres']
                    and 0 < c['movie']['runtime_minutes'] <= minutes for c in data.get('candidates', []))
            sid = session()
            body = dict(mode='discover', input_source='natural_language', session_id=sid,
                        query='想看喜剧，两个小时以内', constraints={'genres': ['恐怖']}, memory_enabled=False)
            r, pending = post('real_model_conflict', body)
            checks['conflict_before_catalog'] = (r.status_code == 200 and pending.get('status') == 'needs_clarification'
                and not pending.get('candidates') and r.headers.get('x-upstream-calls') == '1')
            if not checks['conflict_before_catalog']:
                report['passed'] = False
                return report
            before = report['model_requests']
            answers = [{'question_id': q['question_id'],
                        'option': '按文字条件' if '按文字条件' in q['options'] else q['options'][0]}
                       for q in pending['questions']]
            confirmed = {**body, 'clarification': {'clarification_id': pending['clarification_id'], 'answers': answers}}
            r, first = post('confirm_without_model', confirmed)
            checks['confirmation_no_second_model'] = r.status_code == 200 and report['model_requests'] == before
            checks['real_candidates_hard_filters'] = bool(first.get('candidates')) and valid(first, 120)
            saved = client.put('/me/preferences', headers=headers, json=dict(enabled=True,
                constraints={'exclude_genres': ['恐怖']}, expected_version=0, confirmed=True))
            checks['explicit_memory_saved'] = saved.status_code == 200
            seen_id = first['candidates'][0]['movie']['movie_id'] if first.get('candidates') else 'itunes:1'
            seen = client.post('/feedback', headers=headers, json=dict(event_id='acceptance-seen',
                session_id=sid, movie_id=seen_id, action='seen', confirmed=True))
            checks['confirmed_seen_saved'] = seen.status_code == 200
            r, cross_session = post('seen_cross_session_no_model', dict(mode='discover', input_source='structured',
                session_id=session(), query='直接看看', constraints={'genres': ['喜剧'], 'max_runtime_minutes': 120},
                memory_enabled=True))
            checks['seen_cross_session_excluded'] = (r.status_code == 200 and cross_session.get('memory_used') is True
                and seen_id in cross_session.get('interpretation', {}).get('effective_constraints', {}).get('exclude_movie_ids', [])
                and all(c['movie']['movie_id'] != seen_id for c in cross_session.get('candidates', [])))
            base = {**body, 'constraints': {}}
            r, refined = post('refine_with_saved_memory', {**base, 'query': '改成90分钟以内', 'memory_enabled': True})
            constraints = refined.get('interpretation', {}).get('effective_constraints', {})
            checks['refine_memory_and_filters'] = (r.status_code == 200 and valid(refined, 90)
                and refined.get('memory_used') is True and constraints.get('genres') == ['喜剧']
                and constraints.get('max_runtime_minutes') == 90 and '恐怖' in constraints.get('exclude_genres', []))
            checks['real_refine_applies_seen_memory'] = seen_id in constraints.get('exclude_movie_ids', []) and all(
                c['movie']['movie_id'] != seen_id for c in refined.get('candidates', []))
            before = report['model_requests']
            r, rerolled = post('reroll_no_model', {**base, 'query': '换一组', 'memory_enabled': True})
            old_ids = {c['movie']['movie_id'] for c in first.get('candidates', []) + refined.get('candidates', [])}
            checks['reroll_excludes_displayed_no_model'] = (r.status_code == 200 and report['model_requests'] == before
                and valid(rerolled, 90) and not old_ids.intersection(c['movie']['movie_id'] for c in rerolled.get('candidates', [])))
            r, disabled = post('request_memory_disabled', {**base, 'query': '改成100分钟以内', 'memory_enabled': False})
            constraints = disabled.get('interpretation', {}).get('effective_constraints', {})
            checks['disabled_memory_not_resurrected'] = (r.status_code == 200 and disabled.get('memory_used') is False
                and constraints.get('exclude_genres') == [] and constraints.get('max_runtime_minutes') == 100)
            version = client.get('/me/preferences', headers=headers).json()['version']
            deleted = client.delete(f'/me/preferences?expected_version={version}&confirmed=true', headers=headers)
            checks['delete_saved_preferences'] = deleted.status_code == 200
            r, after_delete = post('refine_after_memory_deletion', {**base, 'query': '改成90分钟以内', 'memory_enabled': True})
            constraints = after_delete.get('interpretation', {}).get('effective_constraints', {})
            checks['deleted_memory_not_resurrected'] = (r.status_code == 200 and valid(after_delete, 90)
                and after_delete.get('memory_used') is False and constraints.get('exclude_genres') == [])
            before = report['model_requests']
            fault[0] = True
            r, failed = post('injected_transport_timeout', {**base, 'query': '改成80分钟以内'})
            checks['controlled_timeout_no_fake_candidates'] = (r.status_code == 504 and failed.get('code') == 'UPSTREAM_TIMEOUT'
                and not failed.get('candidates') and report['model_requests'] == before)
            fault[0] = False
            r, recovered = post('recover_same_session_without_model', {**base, 'query': '换一组'})
            constraints = recovered.get('interpretation', {}).get('effective_constraints', {})
            checks['failure_keeps_context_and_can_recover'] = (r.status_code == 200 and valid(recovered, 90)
                and constraints.get('max_runtime_minutes') == 90 and report['model_requests'] == before)
            checks['no_implicit_memory_write'] = client.get('/me/preferences', headers=headers).json()['enabled'] is False
            checks['delete_test_identity'] = client.delete('/me/data?confirmed=true', headers=headers).status_code == 200
            checks['deleted_token_rejected'] = client.get('/me/preferences', headers=headers).status_code == 401
            headers = None
            report['passed'] = all(checks.values())
            return report
    finally:
        if headers:
            with TestClient(app) as cleanup:
                cleanup.delete('/me/data?confirmed=true', headers=headers)
        fault_client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--max-model-requests', type=int, choices=range(4, 9), default=4)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/mvp/final-agent-acceptance.json')
    args = parser.parse_args(argv)
    if not args.live:
        print('NOT RUN: use --live; no HTTP requests made.')
        return 2
    try:
        settings = ModelSettings.from_env()
    except ValueError:
        print('INVALID_CONFIG: check local model configuration; no HTTP calls made.')
        return 2
    if settings is None:
        print('NOT_CONFIGURED: configure the three LLM variables locally; no HTTP calls made.')
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent, prefix='acceptance-') as folder:
        repo, catalog = Repository(Path(folder) / 'state.sqlite3'), AppleCatalog()
        try:
            report = run_acceptance(catalog, repo, settings, max_model_requests=args.max_model_requests)
            report['mode'] = 'live_model_apple_with_labelled_local_fault'
            report['max_model_requests'] = args.max_model_requests
        finally:
            catalog.client.close()
            repo.close()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(args.output), 'passed': report['passed'],
                      'model_requests': report['model_requests'], 'checks': report['checks']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
