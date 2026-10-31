"""Keyless runtime must preserve the shared graph and its session conditions."""
import json

import httpx

from scripts.movie_config import LOCAL_BASE_URL, LOCAL_MODEL, Settings
from scripts.movie_model import RuntimeInterpreter
from scripts.mvp_intent_contracts import TurnContext
from scripts.s0_contracts import Constraints


def local_settings():
    return Settings(llm_base_url=LOCAL_BASE_URL, llm_model=LOCAL_MODEL)


def test_model_failure_falls_back_without_losing_followup_context():
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("private upstream error", request=request)

    runtime = RuntimeInterpreter(local_settings(), client=httpx.Client(transport=httpx.MockTransport(timeout)))
    context = TurnContext(previous_constraints=Constraints(genres=["喜剧"], exclude_genres=["恐怖"]))
    result = runtime.interpret("改成90分钟以内", context=context)
    assert result.status == "ok" and result.metadata["method"] == "rules-v1"
    assert result.intent.action == "refine"
    assert result.intent.updates.model_dump(exclude_unset=True) == {"max_runtime_minutes": 90}
    assert not result.intent.unhandled and len(calls) == 1
    assert not runtime.verification()["live_verified"]


def test_local_model_reaches_graph_as_real_model_and_keeps_partial_updates():
    def respond(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "constraints": {"max_runtime_minutes": 90}, "unhandled": []})}}]})

    runtime = RuntimeInterpreter(local_settings(), client=httpx.Client(transport=httpx.MockTransport(respond)))
    result = runtime.interpret("改成90分钟以内", context=TurnContext(previous_constraints=Constraints(genres=["喜剧"])))
    assert result.status == "ok" and result.metadata["method"] == "llm-v1"
    assert result.intent.action == "refine"
    assert result.intent.updates.model_dump(exclude_unset=True) == {"max_runtime_minutes": 90}
    assert runtime.verification()["live_verified"] and runtime.verification()["verified_at"]


def test_rule_recovery_keeps_unsupported_requirements_for_confirmation():
    def unavailable(request):
        return httpx.Response(503)

    runtime = RuntimeInterpreter(local_settings(), client=httpx.Client(transport=httpx.MockTransport(unavailable)))
    result = runtime.interpret("豆瓣9分以上的喜剧")
    assert result.intent.updates.genres == ["喜剧"]
    assert result.intent.unhandled and result.metadata["method"] == "rules-v1"


def test_failed_model_can_finish_shared_graph_followup_with_real_catalog_rows():
    from scripts.mvp_workflow import AgentWorkflow
    from scripts.s0_contracts import RecommendationRequest
    from tests.test_mvp_workflow import Catalog

    runtime = RuntimeInterpreter(local_settings(), client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    catalog = Catalog()
    workflow = AgentWorkflow(catalog, lambda: runtime)
    first = workflow.run(RecommendationRequest(mode="discover", query="喜剧，120分钟以内", session_id="offline", input_source="natural_language"))
    followup = workflow.run(RecommendationRequest(mode="discover", query="改成90分钟以内", session_id="offline", input_source="natural_language"), first.context)
    assert followup.status == "ready" and followup.method == "rules-v1"
    assert followup.constraints.genres == ["喜剧"] and followup.constraints.max_runtime_minutes == 90
    assert all(movie.runtime_minutes <= 90 for movie, at in followup.candidates)
