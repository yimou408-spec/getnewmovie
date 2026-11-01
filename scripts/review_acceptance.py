"""Bounded TMDB review acquisition/audit check, separate from multi-source signoff."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from app.services.budget import RequestBudget, budget_scope
from app.services.opinions import OpinionPipeline
from app.services.review_audit import ReviewAudit
from scripts.movie_config import ROOT, Settings
from scripts.movie_catalog_errors import CatalogError
from scripts.s0_contracts import Constraints, SourceEvidenceResult
from scripts.tmdb_reviews import TMDBReviewSource


def run_probe(ids, source, audit=None):
    rows = []
    with budget_scope(RequestBudget(max_http=len(ids), seconds=55)) as budget:
        for mid in ids:
            try:
                raw = source.fetch('tmdb:' + mid, mid)
            except CatalogError as error:
                raw = SourceEvidenceResult(movie_id='tmdb:' + mid, source='TMDB Reviews',
                    status='budget_exhausted' if error.code == 'BUDGET_EXHAUSTED' else 'timeout')
            result = audit.apply(raw) if audit else raw
            summary, _ = OpinionPipeline().run(result.movie_id, Constraints(), [result])
            rows.append(dict(movie_id=result.movie_id, source_status=result.status,
                acquired_review_count=len(raw.evidence),
                safe_excerpt_count=sum(e.spoiler_level == 'safe' for e in result.evidence),
                evidence=[dict(evidence_id=e.evidence_id, author=e.author, url=str(e.url),
                               spoiler_level=e.spoiler_level,
                               independent_source_group=e.independent_source_group) for e in result.evidence],
                opinion_count=len(summary.opinions), comparison_count=len(summary.comparisons),
                summary_status=summary.status, warnings=result.warnings))
    return dict(mode='live_tmdb_review_audit_no_model', checked_at=datetime.now(timezone.utc).isoformat(),
        sample_count=len(ids), requests_made=budget.http_calls, results=rows,
        acquired_review_count=sum(r['acquired_review_count'] for r in rows),
        human_signoff=False, multi_source_acceptance_passed=False,
        limitations=['TMDB acquisition only; no automatic Douban or second-platform verification.',
                     'Different authors do not establish independent publishers.',
                     'An audit file records reviewer assertions; it does not verify them automatically.',
                     'No Apple mapping, production cache update, model calls or preference changes.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--tmdb-id', action='append', required=True)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/opinions/review-acceptance.json')
    args = parser.parse_args(argv)
    ids = args.tmdb_id
    if (not 1 <= len(ids) <= 6 or len(set(ids)) != len(ids)
            or any(not re.fullmatch(r'[1-9][0-9]*', mid) for mid in ids)):
        parser.error('provide 1..6 distinct positive numeric TMDB IDs')
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'artifacts').resolve()):
        parser.error('reports must stay in ignored repository artifacts/')
    if not args.live:
        print('NOT RUN: add --live; no HTTP calls made.')
        return 2
    settings = Settings.load()
    if settings.report().tmdb.state != 'configured':
        print('NOT_CONFIGURED: TMDB_READ_TOKEN; no HTTP calls made.')
        return 2
    report = run_probe(ids, TMDBReviewSource(settings.tmdb_read_token),
                       ReviewAudit(args.audit) if args.audit else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(output), sample_count=report['sample_count'],
        requests_made=report['requests_made'], acquired_review_count=report['acquired_review_count'],
        multi_source_acceptance_passed=False)))
    return 0 if all(r['source_status'] == 'ok' for r in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
