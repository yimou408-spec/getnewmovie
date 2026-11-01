"""One-request structured-output feasibility check for an explicitly configured model."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from scripts.s0_contracts import Constraints
from scripts.movie_config import Settings, is_local_endpoint, valid_model_endpoint


def probe_model(base_url, api_key, model, *, client=None):
    url = urlsplit(base_url)
    if not valid_model_endpoint(base_url):
        raise ValueError("LLM_BASE_URL must be HTTPS or an explicit loopback HTTP endpoint without credentials/query/fragment")
    if client is None:
        with httpx.Client(timeout=30 if is_local_endpoint(base_url) else 20, follow_redirects=False, trust_env=False,
                          proxy=None if is_local_endpoint(base_url) else os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")) as owned_client:
            return probe_model(base_url, api_key, model, client=owned_client)
    payload = {
        "model": model, "max_tokens": 150,
        "messages": [
            {"role": "system", "content": 'Extract constraints as JSON only. Keys: max_runtime_minutes (integer or null), exclude_genres (array). Do not recommend films.'},
            {"role": "user", "content": "想看100分钟以内的电影，不要恐怖片。"},
        ],
    }
    if is_local_endpoint(base_url):
        payload.update(temperature=0, response_format={"type": "json_schema", "json_schema": {
            "name": "probe_constraints", "strict": True, "schema": {"type": "object", "additionalProperties": False,
                "properties": {"max_runtime_minutes": {"type": "integer", "minimum": 1, "maximum": 600},
                    "exclude_genres": {"type": "array", "items": {"type": "string"}}},
                "required": ["max_runtime_minutes", "exclude_genres"]}}})
    started = time.perf_counter()
    result = {"mode": "live", "model": model, "endpoint_host": url.hostname, "requests_made": 1,
              "status": "not_checked", "quality_evaluation": "not_measured"}
    try:
        response = client.post(base_url.rstrip("/") + "/chat/completions", json=payload,
                               headers={"Authorization": "Bearer " + api_key} if api_key else {})
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            return {**result, "status": f"http_{response.status_code}"}
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = Constraints.model_validate_json(content)
        if parsed.max_runtime_minutes != 100 or not {"恐怖", "horror"}.intersection(g.lower() for g in parsed.exclude_genres):
            return {**result, "status": "semantic_mismatch"}
        usage = data.get("usage", {})
        result["usage"] = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                           if isinstance(usage, dict) and isinstance(usage.get(key), int)}
        return {**result, "status": "passed_single_case"}
    except httpx.HTTPError:
        return {**result, "status": "network_error"}
    except (ValueError, KeyError, IndexError, TypeError, ValidationError):
        return {**result, "status": "invalid_structured_output"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/s0/model-report.json"))
    args = parser.parse_args()
    if not args.live:
        print("NOT RUN: add --live to enable one model request.")
        return 2
    settings = Settings.load()
    values = [settings.llm_base_url, settings.llm_api_key, settings.llm_model]
    if settings.report().llm.state != "configured":
        print("NOT_CONFIGURED: use the local model launcher or configure a remote model; no HTTP requests made.")
        return 2
    try:
        result = probe_model(*values)
    except ValueError as error:
        parser.error(str(error))
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "status": result["status"]}, ensure_ascii=False))
    return 0 if result["status"] == "passed_single_case" else 1


if __name__ == "__main__":
    raise SystemExit(main())
