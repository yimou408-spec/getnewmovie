"""M02 target contract and offline examples; not wired into the running API yet."""
import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from scripts.s0_contracts import Constraints, RecommendationRequest, RecommendationResponse, StrictModel

ROOT = Path(__file__).resolve().parents[1]


class IntentDecision(StrictModel):
    """Model supplies intent only. Absent update keys mean keep existing values."""

    action: Literal["recommend", "refine", "reroll", "reset"] = "recommend"
    updates: Constraints = Field(default_factory=Constraints)
    conflicts: list[str] = Field(default_factory=list, max_length=2)
    unhandled: list[str] = Field(default_factory=list, max_length=2)

    @property
    def needs_confirmation(self):
        return bool(self.conflicts or self.unhandled)


class TurnContext(StrictModel):
    previous_constraints: Constraints = Field(default_factory=Constraints)
    displayed_movie_ids: list[str] = Field(default_factory=list)


class IntentCase(StrictModel):
    case_id: str
    description: str
    request: RecommendationRequest
    context: TurnContext = Field(default_factory=TurnContext)
    expected_intent: IntentDecision
    expected_constraints: Constraints
    response: RecommendationResponse


class CaseSet(StrictModel):
    provenance: Literal["synthetic_acceptance_spec"]
    execution_status: Literal["not_run_against_agent"]
    cases: list[IntentCase]


def load_cases(path):
    """Check fixture coherence, never call a model or assert the Agent works."""
    suite = CaseSet.model_validate_json(Path(path).read_text(encoding="utf-8"))
    ids = [case.case_id for case in suite.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case ID")
    for case in suite.cases:
        intent = case.expected_intent
        if intent.action == "reset":
            merged = Constraints().model_dump()
        else:
            base = case.context.previous_constraints if intent.action in ("refine", "reroll") else case.request.constraints
            merged = base.model_dump()
            merged.update(case.request.constraints.model_dump(exclude_unset=True))
            merged.update(intent.updates.model_dump(exclude_unset=True))
            if intent.action == "reroll":
                merged["exclude_movie_ids"] = list(dict.fromkeys([
                    *merged["exclude_movie_ids"], *case.context.displayed_movie_ids,
                ]))
        if Constraints.model_validate(merged) != case.expected_constraints:
            raise ValueError(f"{case.case_id}: inconsistent effective constraints")
        if intent.needs_confirmation != (case.response.status == "needs_clarification"):
            raise ValueError(f"{case.case_id}: inconsistent confirmation state")
        if case.response.data_mode != "synthetic" or case.response.memory_used:
            raise ValueError(f"{case.case_id}: examples must be synthetic without long-term memory")
    return suite.cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-schema", action="store_true")
    args = parser.parse_args()
    folder = ROOT / "contracts/mvp"
    schema_path = folder / "intent-decision.schema.json"
    schema_text = json.dumps(IntentDecision.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    if args.export_schema:
        schema_path.write_text(schema_text, encoding="utf-8")
    elif not schema_path.exists() or schema_path.read_text(encoding="utf-8") != schema_text:
        raise ValueError("Stale MVP schema: run with --export-schema")
    cases = load_cases(folder / "intent-cases.json")
    print(f"PASS: {len(cases)} synthetic specifications; no model/API execution performed.")


if __name__ == "__main__":
    main()
