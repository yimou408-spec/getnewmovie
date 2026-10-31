"""Read-only, bounded TMDB feasibility probe. No auto-retry, no raw response dump."""
import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from scripts.movie_config import Settings

ROOT = Path(__file__).resolve().parents[1]


class BudgetExceeded(RuntimeError):
    pass


class TMDBProbe:
    def __init__(self, token, *, client, max_requests=8):
        self.token, self.client, self.max_requests = token, client, max_requests
        self.calls = 0

    def get(self, path, params):
        if self.calls >= self.max_requests:
            raise BudgetExceeded("HTTP request budget exhausted")
        if not re.fullmatch(r"/(search/movie|movie/\d+)", path):
            raise ValueError("unsupported TMDB probe path")
        self.calls += 1
        try:
            response = self.client.get("https://api.themoviedb.org/3" + path, params=params,
                                       headers={"Authorization": "Bearer " + self.token})
            if response.status_code != 200:
                return {"error": f"http_{response.status_code}"}
            data = response.json()
            return data if isinstance(data, dict) else {"error": "invalid_schema"}
        except httpx.HTTPError:
            return {"error": "network_error"}
        except ValueError:
            return {"error": "invalid_json"}

    def inspect(self, sample, region):
        row = {"sample_id": sample["sample_id"], "query": sample["query"], "year": sample.get("year"),
               "identity_status": "not_checked", "manual_review_required": True, "region": region,
               "availability_status": "unknown", "runtime_minutes": None}
        params = {"query": sample["query"], "language": "zh-CN", "include_adult": "false", "page": 1}
        if sample.get("year"):
            params["year"] = sample["year"]
        started = time.perf_counter()
        search = self.get("/search/movie", params)
        if "error" in search:
            return {**row, "error": search["error"]}
        results = search.get("results")
        if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
            return {**row, "error": "invalid_search_schema"}
        results = [r for r in results if isinstance(r.get("id"), int) and not isinstance(r["id"], bool)]
        if sample.get("year"):
            results = [r for r in results if str(r.get("release_date", "")).startswith(str(sample["year"]) + "-")]
        # Even a single search result is only a candidate, never human-verified identity.
        if sample.get("expected_tmdb_id") is not None:
            matching = [r for r in results if r["id"] == sample["expected_tmdb_id"]]
            if not matching:
                return {**row, "identity_status": "reference_not_found", "candidate_ids": [r["id"] for r in results[:5]]}
            selected = matching[0]
            row["identity_status"] = "matches_reference"
            row["manual_review_required"] = sample.get("reference_status") != "human_verified"
        elif len(results) != 1:
            return {**row, "identity_status": "ambiguous" if results else "not_found",
                    "candidate_ids": [r["id"] for r in results[:5]]}
        else:
            selected = results[0]
            row["identity_status"] = "candidate_unverified"
        details = self.get(f"/movie/{selected['id']}", {
            "language": "zh-CN", "append_to_response": "keywords,alternative_titles,watch/providers",
        })
        if "error" in details:
            return {**row, "error": details["error"]}
        if details.get("id") != selected["id"] or not isinstance(details.get("title"), str):
            return {**row, "error": "invalid_details_schema"}
        runtime = details.get("runtime")
        if isinstance(runtime, bool) or not isinstance(runtime, (int, float)) or runtime <= 0:
            runtime = None
        row.update(movie_id=f"tmdb:{selected['id']}", title=details["title"],
                   runtime_minutes=runtime, latency_ms=round((time.perf_counter() - started) * 1000),
                   release_date=details.get("release_date"),
                   source_url=f"https://www.themoviedb.org/movie/{selected['id']}")
        for key, child, output in (("keywords", "keywords", "keyword_count"),
                                   ("alternative_titles", "titles", "alternative_title_count")):
            group = details.get(key)
            values = group.get(child) if isinstance(group, dict) else None
            row[output] = len(values) if isinstance(values, list) else None
        genres = details.get("genres")
        row["genre_count"] = len(genres) if isinstance(genres, list) else None
        provider_group = details.get("watch/providers")
        regions = provider_group.get("results") if isinstance(provider_group, dict) else None
        local = regions.get(region) if isinstance(regions, dict) else None
        row["availability_schema_valid"] = isinstance(regions, dict)
        row["available_region_count"] = len(regions) if isinstance(regions, dict) else None
        if isinstance(local, dict):
            offers = {kind: len(local[kind]) for kind in ("flatrate", "rent", "buy", "free", "ads")
                      if isinstance(local.get(kind), list) and local[kind]}
            row["provider_offer_counts"] = offers
            row["availability_status"] = "listed_unverified" if offers else "unknown"
            link = local.get("link")
            # Persist only the documented aggregation page, never arbitrary upstream links.
            if isinstance(link, str) and re.match(r"^https://www\.themoviedb\.org/", link):
                row["aggregation_url"] = link
        return row


def summarize(rows):
    details = [r for r in rows if "movie_id" in r]
    return {"sample_count": len(rows), "details_count": len(details),
            "error_count": sum("error" in r for r in rows),
            "ambiguous_count": sum(r["identity_status"] == "ambiguous" for r in rows),
            "unknown_availability_count": sum(r["availability_status"] == "unknown" for r in rows),
            "missing_runtime_count": sum(r["runtime_minutes"] is None for r in details),
            "runtime_coverage_denominator": len(details),
            "manual_review_required_count": sum(r["manual_review_required"] for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Enable real TMDB HTTP requests")
    parser.add_argument("--samples", type=Path, default=ROOT / "data/s0/tmdb_samples.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=8)
    parser.add_argument("--region", default=os.getenv("WATCH_REGION", "CN"))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/s0/tmdb-report.json")
    args = parser.parse_args()
    if not args.live:
        print("NOT RUN: add --live and set TMDB_READ_TOKEN; no HTTP requests made.")
        return 2
    token = Settings.load().tmdb_read_token
    if not token:
        print("NOT_CONFIGURED: TMDB_READ_TOKEN is empty; no HTTP requests made.")
        return 2
    if not (1 <= args.limit <= 30 and 1 <= args.max_requests <= 100 and re.fullmatch(r"[A-Z]{2}", args.region)):
        parser.error("limit 1..30, max-requests 1..100 and uppercase two-letter region required")
    samples = json.loads(args.samples.read_text(encoding="utf-8"))[:args.limit]
    rows = []
    exhausted = False
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False,
                      proxy=os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")) as client:
        probe = TMDBProbe(token, client=client, max_requests=args.max_requests)
        for sample in samples:
            try:
                rows.append(probe.inspect(sample, args.region))
            except BudgetExceeded:
                exhausted = True
                break
    report = {"mode": "live", "checked_at": datetime.now(timezone.utc).isoformat(),
              "region": args.region, "requests_made": probe.calls, "budget_exhausted": exhausted,
              "selected_sample_count": len(samples), "summary": summarize(rows), "results": rows,
              "limitations": ["Search identity and provider availability require human verification.",
                              "Unknown availability is not proof of absence; this probe does not check playback."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "requests_made": probe.calls, "summary": report["summary"]}, ensure_ascii=False))
    return 1 if exhausted or any("error" in r for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
