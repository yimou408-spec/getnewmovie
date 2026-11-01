"""Invented text only: source audit decisions must bind exact acquired evidence."""
import hashlib
import json

import pytest

from app.services.review_audit import ReviewAudit
from app.services.evidence import EvidenceService
from app.services.storage import Repository
from scripts.s0_contracts import SourceEvidenceResult
from tests.test_opinion_synthesis import review
from tests.test_tmdb_adapter import mapped_movie


def entry():
    return review(claim="节奏缓慢。虚构剧情片段。", group=None).model_copy(update={
        "source": "TMDB Reviews", "usage_basis": "provider_terms", "spoiler_level": "unknown"})


def decision(e, **changes):
    return {"movie_id": e.movie_id, "source": e.source, "evidence_id": e.evidence_id,
        "url": str(e.url), "author": e.author,
        "claim_sha256": hashlib.sha256(e.claim.encode('utf-8')).hexdigest(),
        "excerpt": "节奏缓慢。", "spoiler_level": "safe", "independent_source_group": None,
        "independence_basis": None, "reviewer": "offline-auditor", "reviewer_kind": "agent",
        "reviewed_at": "2026-11-01T14:00:00Z", "reason": "Invented style-only sentence, no plot.", **changes}


def write(path, rows):
    path.write_text(json.dumps({"version": 1, "decisions": rows}, ensure_ascii=False), encoding='utf-8')
    return ReviewAudit(path)


def result(e):
    return SourceEvidenceResult(movie_id=e.movie_id, source=e.source, status='ok', evidence=[e])


def test_audit_narrows_exact_acquired_excerpt_without_mutating_raw_source(tmp_path):
    e = entry()
    raw = result(e)
    audited = write(tmp_path/'audit.json', [decision(e)]).apply(raw)
    assert audited.evidence[0].claim == '节奏缓慢。'
    assert audited.evidence[0].spoiler_level == 'safe'
    assert audited.evidence[0].independent_source_group is None
    assert raw.evidence[0].spoiler_level == 'unknown' and raw.evidence[0].claim == e.claim
    assert any('agent' in w and 'offline-auditor' in w for w in audited.warnings)


@pytest.mark.parametrize('change', [
    {'claim': '节奏缓慢。正文已经更新。'}, {'movie_id': 'itunes:102'},
    {'author': 'other'}, {'url': 'https://example.com/changed'}, {'source': 'other'},
    {'evidence_id': 'changed'}, {'usage_basis': 'unverified'},
])
def test_audit_never_upgrades_changed_wrong_or_unpermitted_evidence(tmp_path, change):
    e = entry()
    audit = write(tmp_path/'audit.json', [decision(e)])
    changed = e.model_copy(update=change)
    actual = audit.apply(result(changed)).evidence[0]
    assert actual.claim == changed.claim and actual.spoiler_level == 'unknown'


@pytest.mark.parametrize('changes', [
    {'excerpt': '演技出色。'}, {'independent_source_group': 'publisher-a'},
    {'independent_source_group': 'publisher-a', 'independence_basis': 'different username'},
    {'reviewer_kind': 'model'}, {'claim_sha256': 'not-a-hash'},
])
def test_invalid_fabricated_or_unsubstantiated_decisions_fail_closed(tmp_path, changes):
    e = entry()
    audit = write(tmp_path/'audit.json', [decision(e, **changes)])
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'unknown'


def test_verified_group_requires_explicit_original_publisher_evidence(tmp_path):
    e = entry()
    audit = write(tmp_path/'audit.json', [decision(e, independent_source_group='publisher-a',
        independence_basis={'publisher': 'Offline publisher A', 'original_url': 'https://example.com/original',
                            'rationale': 'Offline verification: original byline and publication, no syndication.'})])
    assert audit.apply(result(e)).evidence[0].independent_source_group == 'publisher-a'


def test_revoked_missing_malformed_and_duplicate_decisions_do_not_leave_old_clearance(tmp_path):
    e, path = entry(), tmp_path/'audit.json'
    audit = write(path, [decision(e)])
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'safe'
    write(path, [])
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'unknown'
    write(path, [decision(e), decision(e)])
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'unknown'
    path.write_text('invalid', encoding='utf-8')
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'unknown'
    path.unlink()
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'unknown'


def test_failed_stale_sources_and_explicit_spoilers_are_not_promoted(tmp_path):
    e = entry()
    audit = write(tmp_path/'audit.json', [decision(e)])
    for update in ({'status': 'timeout'}, {'cache_status': 'stale'}):
        assert audit.apply(result(e).model_copy(update=update)).evidence[0].spoiler_level == 'unknown'
    e.spoiler_level = 'contains_spoilers'
    assert audit.apply(result(e)).evidence[0].spoiler_level == 'contains_spoilers'


def test_service_applies_current_decision_after_cache_without_persisting_clearance(tmp_path):
    movie = mapped_movie()
    e = entry()
    e.movie_id = movie.movie_id
    path = tmp_path/'audit.json'
    audit = write(path, [decision(e)])
    class Adapter:
        source = e.source
        identity_provider = 'tmdb'
        def fetch(self, movie_id, external_id):
            return result(e)
    with_repo = Repository(tmp_path/'store.sqlite3')
    service = EvidenceService(with_repo, {'tmdb_reviews': Adapter()}, review_audit=audit)
    first = next(r for r in service.collect(movie) if r.source == e.source)
    assert first.evidence[0].spoiler_level == 'safe'
    cached = with_repo.cache_get(movie.movie_id, e.source, '129')[1]
    assert cached['evidence'][0]['spoiler_level'] == 'unknown'
    write(path, [])
    second = next(r for r in service.collect(movie) if r.source == e.source)
    assert second.cache_status == 'fresh' and second.evidence[0].spoiler_level == 'unknown'
    with_repo.close()


def test_production_api_uses_explicit_audit_path_and_preserves_unknown_independence(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from scripts import movie_server
    from scripts.movie_config import Settings
    from tests.test_movie_intent import CatalogDouble
    e = entry()
    audit_path = tmp_path/'audit.json'
    write(audit_path, [decision(e)])
    class Adapter:
        source = e.source
        identity_provider = 'tmdb'
        def fetch(self, movie_id, external_id):
            return result(e)
    monkeypatch.setenv('MOVIE_REVIEW_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(movie_server, 'AppleCatalog', CatalogDouble)
    monkeypatch.setattr('app.services.evidence.configured_adapters', lambda **kwargs: {'tmdb_reviews': Adapter()})
    repo = Repository(tmp_path/'api.sqlite3')
    repo.register_mapping('itunes:101', mapped_movie().external_ids[0])
    with TestClient(movie_server.create_app(settings=Settings(), repository=repo)) as client:
        response = client.post('/recommendations', json={'mode': 'discover', 'query': 'offline', 'session_id': 'audit'})
        assert response.status_code == 200
        data = response.json()
        r = next(r for r in data['source_results'] if r['source'] == e.source and r['movie_id'] == e.movie_id)
        assert r['evidence'][0]['claim'] == '节奏缓慢。'
        summary = next(c for c in data['candidates'] if c['movie']['movie_id'] == e.movie_id)['opinion_summary']
        assert summary['status'] == 'independence_unknown'
        assert not summary['synthetic'] and not summary['comparisons']
    repo.close()
