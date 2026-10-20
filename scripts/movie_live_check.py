"""Opt-in real-network acceptance: python -m scripts.movie_live_check. No fixtures."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from scripts.movie_catalog import GENRES, MOODS


def main():
    client = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=45)
    report = []
    def recommend(constraints):
        for attempt in range(3):
            response = client.post("/recommendations", json={"mode": "discover", "query": "live acceptance", "session_id": "live-acceptance", "constraints": constraints})
            if response.status_code == 503 and response.json().get("code") == "UPSTREAM_RATE_LIMIT" and attempt < 2:
                print("Provider budget reached; allowing next minute window", flush=True)
                time.sleep(60)
                continue
            response.raise_for_status()
            data = response.json()
            assert data["data_mode"] in ("live", "cached")
            for candidate in data["candidates"]:
                m = candidate["movie"]
                assert m["movie_id"].startswith("itunes:") and m["source_url"].startswith("https://itunes.apple.com/")
                assert m["ratings"] == []
                if constraints.get("genres"):
                    assert set(m["genres"]) & set(constraints["genres"])
                if constraints.get("moods"):
                    assert set(m["genres"]) & set().union(*(MOODS[x] for x in constraints["moods"]))
                if constraints.get("max_runtime_minutes"):
                    assert 0 < m["runtime_minutes"] <= constraints["max_runtime_minutes"]
                assert m["movie_id"] not in constraints.get("exclude_movie_ids", [])
                era = constraints.get("era", "any")
                if era != "any":
                    low, high = {"recent": (2020, datetime.now(timezone.utc).year), "2000s": (2000, 2019), "classic": (1888, 1999)}[era]
                    assert m["year"] is not None and low <= m["year"] <= high
            report.append({"constraints": constraints, **data})
            print(json.dumps({"constraints": constraints, "catalog": data["catalog_size"], "matched": data["matched_count"], "movies": [c["movie"]["title"] for c in data["candidates"]]}, ensure_ascii=False), flush=True)
            return data
    for genre in GENRES:
        recommend({"genres": [genre]})
    for mood in MOODS:
        recommend({"moods": [mood]})
    for duration in [90, 120, 150]:
        recommend({"max_runtime_minutes": duration})
    assert recommend({"genres": ["恐怖"], "moods": ["感动一下"]})["status"] == "empty"
    for order in ["balanced", "popular"]:
        base = recommend({"sort_by": order})
        excluded = [c["movie"]["movie_id"] for c in base["candidates"]]
        recommend({"sort_by": order, "exclude_movie_ids": excluded})
        for era in ["recent", "2000s", "classic"]:
            recommend({"sort_by": order, "era": era})
    path = Path("artifacts/live-catalog/filter-acceptance.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS {len(report)} real-network filter cases; evidence: {path}")


if __name__ == "__main__":
    main()
