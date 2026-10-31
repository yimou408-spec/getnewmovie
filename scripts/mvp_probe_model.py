"""Explicit, bounded live intent probe. Missing configuration makes no HTTP calls."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.mvp_intent_contracts import ROOT, load_cases
from scripts.mvp_model import ModelAdapter, ModelSettings, PROMPT_VERSION


def run_probe(settings, *, case_ids, max_requests=1, client=None):
    cases = {c.case_id: c for c in load_cases(ROOT / "contracts/mvp/intent-cases.json")}
    if not case_ids or len(set(case_ids)) != len(case_ids) or any(cid not in cases for cid in case_ids):
        raise ValueError("Select unique case IDs from E01–E09")
    adapter = ModelAdapter(settings, client=client, max_requests=max_requests)
    rows = []
    for case_id in case_ids:
        if adapter.requests_made >= max_requests:
            rows.append({"case_id": case_id, "status": "not_run_budget"})
            continue
        case = cases[case_id]
        result = adapter.interpret(case.request.query, context=case.context, picks=case.request.constraints)
        status = result.status
        if status == "ok":
            actual, expected = result.intent, case.expected_intent
            def normalized(updates):
                return {k: sorted(v) if isinstance(v, list) else v
                        for k, v in updates.model_dump(exclude_unset=True).items()}
            matches = (actual.action == expected.action and normalized(actual.updates) == normalized(expected.updates)
                       and bool(actual.conflicts) == bool(expected.conflicts)
                       and bool(actual.unhandled) == bool(expected.unhandled))
            status = "passed" if matches else "semantic_mismatch"
        rows.append({"case_id": case_id, "status": status, **result.metadata})
    return {"mode": "live_model_synthetic_inputs", "prompt_version": PROMPT_VERSION,
            "checked_at": datetime.now(timezone.utc).isoformat(), "requests_made": adapter.requests_made,
            "max_requests": max_requests, "cases": rows,
            "passed": all(row["status"] == "passed" for row in rows),
            "agent_acceptance": "not_tested", "cost": "unknown; check provider billing"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", action="append", choices=[f"E{i:02}" for i in range(1, 10)])
    parser.add_argument("--max-requests", type=int, choices=range(1, 21), default=1)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--timeout-seconds", type=float, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/mvp/model-report.json")
    args = parser.parse_args(argv)
    if not args.live:
        print("NOT RUN: use --live for a bounded model request; no HTTP calls made.")
        return 2
    try:
        settings = ModelSettings.from_env(timeout_seconds=args.timeout_seconds, max_output_tokens=args.max_output_tokens)
    except ValueError:
        print("INVALID_CONFIG: check HTTPS base URL, model, timeout and token budget; no HTTP calls made.")
        return 2
    if settings is None:
        print("NOT_CONFIGURED: fill LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in the project .env or process environment; no HTTP calls made.")
        return 2
    report = run_probe(settings, case_ids=args.case or ["E02"], max_requests=args.max_requests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "requests_made": report["requests_made"], "passed": report["passed"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
