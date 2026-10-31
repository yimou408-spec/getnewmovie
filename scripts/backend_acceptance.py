"""Repeatable real-catalog + persistence smoke; never calls a paid model.

An optional live mode is explicit and bounded by the shared request ledger.
Reports contain checks and counters, not bearer tokens or user prose.
"""
import argparse
import json
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.services.storage import Repository
from scripts.movie_catalog import AppleCatalog
from scripts.movie_server import create_app

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/backend-acceptance/live-smoke.json")
    args = parser.parse_args()
    if not args.live:
        print("NOT RUN: add --live; no HTTP requests made.")
        return 2
    report = {"mode": "live_apple_no_model", "checks": {}, "upstream_calls": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent, prefix="smoke-") as folder:
        repo = Repository(Path(folder) / "smoke.sqlite3")
        catalog = AppleCatalog()
        try:
            with TestClient(create_app(catalog, repository=repo)) as client:
                identity = client.post("/identities").json()
                headers = {"Authorization": "Bearer " + identity["identity_token"]}
                sid = client.post("/sessions", headers=headers).json()["session_id"]
                preferences = dict(enabled=True, constraints={"genres": ["喜剧"], "max_runtime_minutes": 120}, confirmed=True, expected_version=0)
                report["checks"]["save_preferences"] = client.put("/me/preferences", headers=headers, json=preferences).status_code == 200
                body = dict(mode="discover", query="直接看看", input_source="structured", session_id=sid, memory_enabled=True, constraints={})
                response = client.post("/recommendations", headers=headers, json=body)
                report["upstream_calls"] += int(response.headers.get("x-upstream-calls", 0))
                data = response.json()
                report["http_status"] = response.status_code
                if response.status_code == 200:
                    report["checks"]["real_candidates"] = bool(data["candidates"]) and all(c["movie"]["movie_id"].startswith("itunes:") for c in data["candidates"])
                    report["checks"]["saved_hard_filters"] = data["memory_used"] and all("喜剧" in c["movie"]["genres"] and c["movie"]["runtime_minutes"] <= 120 for c in data["candidates"])
                    report["candidate_count"] = len(data["candidates"])
                    report["source_statuses"] = sorted({r["status"] for r in data["source_results"]})
                    if data["candidates"]:
                        mid = data["candidates"][0]["movie"]["movie_id"]
                        feedback = dict(event_id="smoke-seen", session_id=sid, movie_id=mid, action="seen", confirmed=True)
                        first = client.post("/feedback", headers=headers, json=feedback)
                        again = client.post("/feedback", headers=headers, json=feedback)
                        report["checks"]["feedback_idempotent"] = first.status_code == 200 and first.json() == again.json()
                        next_sid = client.post("/sessions", headers=headers).json()["session_id"]
                        next_response = client.post("/recommendations", headers=headers, json={**body, "session_id": next_sid})
                        report["upstream_calls"] += int(next_response.headers.get("x-upstream-calls", 0))
                        report["checks"]["seen_cross_session"] = next_response.status_code == 200 and all(c["movie"]["movie_id"] != mid for c in next_response.json()["candidates"])
                else:
                    report["checks"]["real_candidates"] = False
                    report["error_code"] = data.get("code")
                report["checks"]["delete_identity"] = client.delete("/me/data?confirmed=true", headers=headers).status_code == 200
                report["checks"]["deleted_token_rejected"] = client.get("/me/preferences", headers=headers).status_code == 401
            report["passed"] = all(report["checks"].values())
        finally:
            catalog.client.close()
            repo.close()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
