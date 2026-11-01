"""Explicit live Apple + TMDB recommendation smoke for registered mappings.

Uses the real production services without a paid model. Never registers mappings
or changes personal data; writes a local report containing metadata/checks only.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from fastapi.testclient import TestClient

from app.services.evidence import EvidenceService
from app.services.storage import Repository
from scripts.movie_catalog import AppleCatalog
from scripts.movie_server import create_app
from scripts.s0_contracts import RecommendationResponse
from scripts.tmdb_adapter import TMDBSource

ROOT = Path(__file__).resolve().parents[1]


def evaluate_responses(first, second, movie_ids):
    checks = {"http_success": first.status_code == second.status_code == 200}
    if not checks["http_success"]:
        return {**checks, "mapped_candidates": False, "fresh_cache": False}
    try:
        a, b = [RecommendationResponse.model_validate(response.json()).model_dump(mode="json")
                for response in (first, second)]
    except ValueError:
        return {**checks, "response_contract": False}
    checks["response_contract"] = True
    expected = set(movie_ids)
    candidates = {c["movie"]["movie_id"]: c for c in b["candidates"]}
    initial = {c["movie"]["movie_id"]: c for c in a["candidates"]}
    sources = [r for r in b.get("source_results", []) if r["source"] == "TMDB" and r["movie_id"] in expected]
    evidence = {e["evidence_id"]: e for e in b["evidence"]}
    provider_ids = {mid: {link["external_id"] for link in c["movie"].get("external_ids") or []
                         if link["provider"] == "tmdb" and link["status"] == "confirmed"}
                    for mid, c in candidates.items()}
    checks["mapped_candidates"] = expected <= candidates.keys() and all(
        any(link["provider"] == "tmdb" and link["status"] == "confirmed"
            for link in candidates[mid]["movie"].get("external_ids") or []) for mid in expected)
    checks["fresh_cache"] = (expected <= {r["movie_id"] for r in sources}
        and all(r["status"] == "ok" and r["cache_status"] == "fresh" and r["evidence"] for r in sources))
    checks["same_movie_evidence"] = bool(sources) and all(
        e["movie_id"] == r["movie_id"] and e["source"] == "TMDB"
        and e["kind"] == "metadata" and e["spoiler_level"] == "safe"
        and e["source_content_id"] in provider_ids.get(r["movie_id"], set())
        and e["url"] == f"https://www.themoviedb.org/movie/{e['source_content_id']}"
        and evidence.get(e["evidence_id"]) == e for r in sources for e in r["evidence"])
    checks["no_ratings_or_reviews"] = not any(c["movie"]["ratings"] for c in b["candidates"]) and not any(
        e["kind"] in {"rating", "review"} for e in b["evidence"])
    checks["stable_apple_facts"] = expected <= initial.keys() and all(
        all(initial[mid]["movie"][key] == candidates[mid]["movie"][key]
            for key in ("title", "year", "runtime_minutes", "director")) for mid in expected if mid in candidates)
    checks["second_request_zero_http"] = second.headers.get("x-upstream-calls") == "0"
    checks["no_memory_used"] = not a["memory_used"] and not b["memory_used"]
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--movie-id", action="append", default=[])
    parser.add_argument("--database", type=Path, default=Path(os.getenv("MOVIE_DB_PATH") or ROOT / "artifacts/state/movie.sqlite3"))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/tmdb-mapping/recommendation-smoke.json")
    args = parser.parse_args()
    if not args.live:
        print("NOT RUN: add --live and confirmed --movie-id values; no HTTP requests made.")
        return 2
    token = os.getenv("TMDB_READ_TOKEN", "").strip()
    if not token:
        print("NOT_CONFIGURED: TMDB_READ_TOKEN is empty; no HTTP requests made.")
        return 2
    if (not 1 <= len(args.movie_id) <= 3 or len(set(args.movie_id)) != len(args.movie_id)
            or any(not re.fullmatch(r"itunes:[1-9][0-9]*", mid) for mid in args.movie_id)):
        parser.error("provide 1..3 distinct numeric Apple --movie-id values")
    if not args.database.is_file():
        print("NOT_CONFIGURED: mapping database does not exist; no HTTP requests made.")
        return 2
    repo = Repository(args.database)
    catalog = AppleCatalog()
    try:
        for mid in args.movie_id:
            if not any(link.provider == "tmdb" and link.status == "confirmed" for link in repo.mappings(mid)):
                print("NOT_CONFIGURED: each movie needs a confirmed TMDB mapping; no HTTP requests made.")
                return 2
        service = EvidenceService(repo, {"tmdb": TMDBSource(token)})
        body = dict(mode="watchlist", query="核验已确认影片资料", session_id="tmdb-live-smoke",
                    memory_enabled=False, watchlist_movie_ids=args.movie_id)
        with TestClient(create_app(catalog, repository=repo, evidence_service=service)) as client:
            first = client.post("/recommendations", json=body)
            second = client.post("/recommendations", json=body)
        checks = evaluate_responses(first, second, args.movie_id)
        report = {"mode": "live_apple_tmdb_no_model", "checked_at": datetime.now(timezone.utc).isoformat(),
                  "checks": checks, "passed": all(checks.values()), "requests": []}
        for response in (first, second):
            try:
                data = response.json()
                if not isinstance(data, dict):
                    data = {}
            except ValueError:
                data = {}
            report["requests"].append({"status": response.status_code,
                "http_calls": int(response.headers.get("x-upstream-calls", 0)),
                "candidates": data.get("candidates", []), "evidence": data.get("evidence", []),
                "source_results": data.get("source_results", []), "error_code": data.get("code")})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(args.output), "passed": report["passed"], "checks": checks,
                          "http_calls": [row["http_calls"] for row in report["requests"]]}))
        return 0 if report["passed"] else 1
    finally:
        catalog.client.close()
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
