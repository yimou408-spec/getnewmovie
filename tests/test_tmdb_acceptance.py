"""Bounded acceptance must opt in and verify source/cache behavior, offline here."""
from fastapi.testclient import TestClient
import httpx
import pytest

from scripts.tmdb_acceptance import evaluate_responses, main


def test_tmdb_acceptance_requires_live_and_token_without_network(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["acceptance"])
    assert main() == 2
    assert "NOT RUN" in capsys.readouterr().out
    monkeypatch.delenv("TMDB_READ_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["acceptance", "--live", "--movie-id", "itunes:1"])
    assert main() == 2
    assert "NOT_CONFIGURED" in capsys.readouterr().out


def test_response_checks_reject_stale_wrong_movie_or_added_ratings():
    from tests.test_tmdb_adapter import source, payload, mapped_movie
    from app.services.evidence import EvidenceService
    from app.services.storage import Repository
    from scripts.movie_server import create_app
    from tests.test_movie_intent import CatalogDouble
    import httpx
    import copy
    repo = Repository(":memory:")
    repo.register_mapping("itunes:101", mapped_movie().external_ids[0])
    service = EvidenceService(repo, {"tmdb": source(lambda r: httpx.Response(200, json=payload()))})
    client = TestClient(create_app(CatalogDouble(), repository=repo, evidence_service=service))
    body = dict(mode="discover", query="offline", session_id="legacy")
    first, second = [client.post("/recommendations", json=body) for _ in range(2)]
    checks = evaluate_responses(first, second, ["itunes:101"])
    assert all(checks.values())
    stale = copy.deepcopy(second.json())
    next(r for r in stale["source_results"] if r["source"] == "TMDB")["cache_status"] = "stale"
    bad = httpx.Response(200, json=stale, headers={"x-upstream-calls": "0"})
    assert not all(evaluate_responses(first, bad, ["itunes:101"]).values())
    assert not evaluate_responses(first, second, ["itunes:999"])["mapped_candidates"]
    rated = copy.deepcopy(second.json())
    rated["candidates"][0]["movie"]["ratings"] = [{"source": "Fake score"}]
    assert not all(evaluate_responses(first, httpx.Response(200, json=rated), ["itunes:101"]).values())


@pytest.mark.parametrize("change", ["empty_evidence", "wrong_provider_id", "wrong_movie", "invalid_json", "missing_fields"])
def test_acceptance_never_passes_invalid_or_misbound_evidence(change):
    import copy
    from tests.test_tmdb_adapter import mapped_movie, payload, source
    from app.services.evidence import EvidenceService
    from app.services.storage import Repository
    from scripts.movie_server import create_app
    from tests.test_movie_intent import CatalogDouble
    repo = Repository(":memory:")
    repo.register_mapping("itunes:101", mapped_movie().external_ids[0])
    client = TestClient(create_app(CatalogDouble(), repository=repo,
        evidence_service=EvidenceService(repo, {"tmdb": source(lambda r: httpx.Response(200, json=payload()))})))
    body = dict(mode="discover", query="offline", session_id="legacy")
    first, second = [client.post("/recommendations", json=body) for _ in range(2)]
    data = copy.deepcopy(second.json())
    record = next(r for r in data["source_results"] if r["source"] == "TMDB" and r["movie_id"] == "itunes:101")
    if change == "empty_evidence":
        record["evidence"] = []
    elif change == "wrong_provider_id":
        record["evidence"][0]["source_content_id"] = "999"
        next(e for e in data["evidence"] if e["source"] == "TMDB")["source_content_id"] = "999"
    elif change == "wrong_movie":
        record["evidence"][0]["movie_id"] = "itunes:102"
    elif change == "missing_fields":
        data = {}
    bad = httpx.Response(200, json=data, headers={"x-upstream-calls": "0"})
    if change == "invalid_json":
        bad = httpx.Response(200, text="not-json", headers={"x-upstream-calls": "0"})
    assert not all(evaluate_responses(first, bad, ["itunes:101"]).values())


def test_acceptance_missing_database_or_mapping_makes_no_requests(monkeypatch, tmp_path, capsys):
    from app.services.storage import Repository
    monkeypatch.setenv("TMDB_READ_TOKEN", "OFFLINE_SECRET")
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: pytest.fail("No network allowed"))
    path = tmp_path / "mapping.sqlite3"
    args = ["acceptance", "--live", "--movie-id", "itunes:1", "--database", str(path)]
    monkeypatch.setattr("sys.argv", args)
    assert main() == 2 and not path.exists()
    repo = Repository(path)
    repo.close()
    assert main() == 2
    assert "confirmed TMDB mapping" in capsys.readouterr().out


def test_acceptance_records_http_failure_as_failed_checks():
    error = httpx.Response(503, json={"code": "UPSTREAM_UNAVAILABLE"})
    assert not all(evaluate_responses(error, error, ["itunes:1"]).values())


def test_review_acceptance_checks_attribution_cache_binding_and_missing_coverage():
    import copy
    from scripts.tmdb_acceptance import evaluate_review_responses
    from tests.test_tmdb_adapter import mapped_movie
    from tests.test_tmdb_reviews import source, payload
    from app.services.evidence import EvidenceService
    from app.services.storage import Repository
    from scripts.movie_server import create_app
    from tests.test_movie_intent import CatalogDouble
    repo = Repository(':memory:')
    repo.register_mapping('itunes:101', mapped_movie().external_ids[0])
    client = TestClient(create_app(CatalogDouble(), repository=repo,
        evidence_service=EvidenceService(repo, {'tmdb_reviews': source(payload())})))
    body = dict(mode='discover', query='offline', session_id='legacy')
    first, second = [client.post('/recommendations', json=body) for _ in range(2)]
    assert all(evaluate_review_responses(first, second, ['itunes:101']).values())
    for mutation in ['missing_author', 'no_reviews', 'wrong_review_url', 'stale', 'unsafe_claim']:
        data = copy.deepcopy(second.json())
        record = next(r for r in data['source_results'] if r['source'] == 'TMDB Reviews')
        entry = record['evidence'][0]
        if mutation == 'missing_author':
            entry['author'] = None
        elif mutation == 'no_reviews':
            record['evidence'] = []
        elif mutation == 'wrong_review_url':
            entry['url'] = 'https://www.themoviedb.org/review/' + 'b' * 24
        elif mutation == 'stale':
            record['cache_status'] = 'stale'
        else:
            entry['spoiler_level'] = 'safe'
        changed = httpx.Response(200, json=data, headers={'x-upstream-calls': '0'})
        assert not all(evaluate_review_responses(first, changed, ['itunes:101']).values()), mutation
