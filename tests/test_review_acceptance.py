"""Offline transport and report tests; never contact the real provider."""
import json

from scripts import review_acceptance
from tests.test_tmdb_reviews import source, payload


def test_probe_preserves_failed_sample_denominator_and_excludes_prose():
    adapter = source(payload())
    class Mixed:
        def fetch(self, movie_id, external_id):
            r = adapter.fetch(movie_id, external_id)
            return r
    report = review_acceptance.run_probe(['129', '130'], Mixed())
    assert report['sample_count'] == 2
    assert report['acquired_review_count'] == 1
    assert [r['source_status'] for r in report['results']] == ['ok', 'parse_error']
    assert report['multi_source_acceptance_passed'] is False
    assert 'Invented opinion' not in json.dumps(report)
    assert not report['human_signoff']


def test_cli_requires_live_and_configuration_before_network(tmp_path, monkeypatch):
    from scripts.movie_config import Settings
    monkeypatch.setattr(review_acceptance.Settings, 'load', lambda: Settings())
    assert review_acceptance.main(['--tmdb-id', '129']) == 2
    assert review_acceptance.main(['--live', '--tmdb-id', '129']) == 2


def test_cli_rejects_unbounded_inputs_and_tracked_report_paths(tmp_path, monkeypatch):
    import pytest
    for args in (['--live', '--tmdb-id', '129', '--tmdb-id', '129'],
                 ['--live', '--tmdb-id', 'not-an-id'],
                 ['--live', '--tmdb-id', '129', '--output', 'data/report.json']):
        with pytest.raises(SystemExit):
            review_acceptance.main(args)


def test_probe_keeps_budget_failures_in_report_instead_of_aborting():
    from scripts.movie_catalog_errors import CatalogError
    class Exhausted:
        def fetch(self, movie_id, external_id):
            raise CatalogError('BUDGET_EXHAUSTED', 'offline exhaustion', 503)
    report = review_acceptance.run_probe(['129', '130'], Exhausted())
    assert report['sample_count'] == 2
    assert all(r['source_status'] == 'budget_exhausted' for r in report['results'])
