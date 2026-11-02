"""Opt-in bounded Douban probe. Set DOUBAN_PROBE_NETWORK=direct and use --live.

No retries, redirects, cookies, or challenge bypass; no review text in reports.
"""
import argparse
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.douban_adapter import DoubanAdapter

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = (
    {"query": "Before Sunrise", "year": 1995},
    {"query": "Little Women", "year": 2019},
    {"query": "Anora", "year": 2024},
)


def run_probe(client, *, max_requests=9):
    adapter = DoubanAdapter(client, max_requests=max_requests)
    rows = []
    for sample in SAMPLES:
        match = adapter.search([sample["query"]], sample["year"])
        row = {**sample, "identity_status": match.status, "candidates": match.candidates,
               "manual_review_required": True, "subject_id": match.subject_id,
               "score_count": 0, "review_excerpt_count": 0, "full_text_count": 0,
               "quotation_count": 0, "synopsis_status": "not_parsed",
               "evaluation_status": "not_attempted"}
        if match.subject_id:
            result = adapter.fetch(f"douban:{match.subject_id}", match.subject_id)
            row.update(evaluation_status=result.status, score_count=len(result.ratings),
                       review_excerpt_count=sum(e.kind == "review" and e.granularity == "excerpt" for e in result.evidence),
                       evidence_urls=sorted({str(e.url) for e in result.evidence}), warnings=result.warnings)
        rows.append(row)
    observations = [item.as_dict() for item in adapter.observations]
    return {
        "mode": "live", "checked_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(rows), "request_budget": max_requests, "requests_made": adapter.calls,
        "results": rows, "observations": observations,
        "summary": {
            "identity_candidates": sum(r["identity_status"] == "candidate" for r in rows),
            "rating_count": sum(r["score_count"] for r in rows),
            "review_excerpt_count": sum(r["review_excerpt_count"] for r in rows), "full_text_count": 0,
            "redirect_count": sum(o["http_status"] in {301, 302, 303, 307, 308} for o in observations),
            "rate_limit_count": sum(o["http_status"] == 429 for o in observations),
            "timeout_count": sum(o["status"] == "timeout" for o in observations),
            "access_limited_count": sum(o["status"] == "access_limited" for o in observations),
        },
        "limitations": [
            "Search candidates are not verified external identity mappings.",
            "No raw HTML, review text, cookies, or credentials are stored in the report.",
            "Synopsis and full review retrieval are not implemented; absence is not inferred.",
            "Review excerpts are unreviewed for spoilers and are not cleared for publication.",
            "Network availability does not establish permission to store, quote, or redistribute content.",
        ],
    }


def run_subject_probe(client, subject_id, *, max_requests=4):
    """Check one explicit ID twice only if the first pair yields usable data.

    Directly supplying an ID does not verify cross-provider identity. Never retry
    blocked/empty/failed pairs; two successes remain a small temporal sample.
    """
    if not re.fullmatch(r'[1-9][0-9]*', subject_id):
        raise ValueError('invalid subject ID')
    adapter = DoubanAdapter(client, max_requests=max_requests)
    rows = []
    for round_number in (1, 2):
        if adapter.calls + 2 > max_requests:
            break
        result = adapter.fetch('douban:' + subject_id, subject_id)
        scores = len(result.ratings)
        reviews = sum(e.kind == 'review' and e.granularity == 'excerpt' for e in result.evidence)
        pair_ok = (result.status == 'ok' and scores > 0 and reviews > 0
                   and all(o.status == 'ok' for o in adapter.observations[-2:]))
        rows.append(dict(round=round_number, evaluation_status=result.status,
            score_count=scores, review_excerpt_count=reviews, both_endpoints_parsed=pair_ok,
            evidence_urls=sorted({str(e.url) for e in result.evidence}), warnings=result.warnings))
        if not pair_ok:
            break
    return dict(mode='live_explicit_subject', checked_at=datetime.now(timezone.utc).isoformat(),
        subject_id=subject_id, identity_status='pending_review', sample_count=1,
        request_budget=max_requests, requests_made=adapter.calls, results=rows,
        observations=[o.as_dict() for o in adapter.observations],
        two_round_acquisition_passed=len(rows) == 2 and all(r['both_endpoints_parsed'] for r in rows),
        multi_source_acceptance_passed=False,
        summary=dict(rating_count=sum(r['score_count'] for r in rows),
            review_excerpt_count=sum(r['review_excerpt_count'] for r in rows),
            access_limited_count=sum(o.status == 'access_limited' for o in adapter.observations)),
        limitations=['Explicit source ID is not a confirmed Apple/TMDB identity mapping.',
            'Two successful immediate rounds cannot establish sustained availability.',
            'No raw HTML, review text, cookies or credentials are stored in reports.',
            'Acquisition does not establish publication permission, independence or spoiler clearance.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/douban/y02-report.json")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-requests", type=int, default=9)
    parser.add_argument("--proxy", help="Explicit proxy URL for network mode proxy")
    parser.add_argument("--subject-id", help="Check one explicit Douban ID; stop after failed first pair")
    args = parser.parse_args()
    if not args.live:
        print("NOT RUN: add --live; no HTTP requests made.")
        return 2
    network = os.getenv("DOUBAN_PROBE_NETWORK", "")
    if network not in {"direct", "proxy"} or network == "proxy" and not args.proxy:
        print("NOT_CONFIGURED: set DOUBAN_PROBE_NETWORK=direct or proxy (with --proxy).")
        return 2
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 30 or not 1 <= args.max_requests <= 30:
        parser.error("timeout must be 0..30 seconds; max-requests must be 1..30")
    if args.subject_id and (not re.fullmatch(r'[1-9][0-9]*', args.subject_id) or args.max_requests < 2):
        parser.error('--subject-id must be numeric and needs at least two requests')
    if network == "direct" and args.proxy:
        parser.error("--proxy requires DOUBAN_PROBE_NETWORK=proxy")
    started = time.perf_counter()
    with httpx.Client(timeout=args.timeout, trust_env=False, follow_redirects=False,
                      proxy=args.proxy, headers={"User-Agent": "getnewmovie-feasibility/1.1"}) as client:
        report = (run_subject_probe(client, args.subject_id, max_requests=min(args.max_requests, 4))
                  if args.subject_id else run_probe(client, max_requests=args.max_requests))
    report["network_mode"] = network
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "requests_made": report["requests_made"],
                      "summary": report["summary"]}, ensure_ascii=False))
    passed = (report['two_round_acquisition_passed'] if args.subject_id else
              all(r["review_excerpt_count"] > 0 for r in report["results"]))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
