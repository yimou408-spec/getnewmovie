"""M05 actual graph execution using offline model and catalog doubles."""
from threading import RLock

from scripts.mvp_intent_contracts import IntentDecision
from scripts.mvp_model import ModelResult
from scripts.mvp_workflow import AgentContext, AgentWorkflow
from scripts.s0_contracts import Constraints, RecommendationRequest, Movie


class Catalog:
    def __init__(self):
        self.lock, self.calls = RLock(), 0

    def pool(self, genres):
        self.calls += 1
        return [(Movie(movie_id=f"itunes:{i}", title=f"Offline {i}", runtime_minutes=minutes,
                       genres=[genre], year=2024), "2026-10-26T00:00:00Z")
                for i, minutes, genre in [(1, 80, "喜剧"), (2, 110, "喜剧"), (3, 85, "喜剧"), (4, 80, "恐怖")]]


class Model:
    def __init__(self, intent=None, status="ok"):
        self.intent, self.status, self.calls = intent, status, 0

    def interpret(self, query, **kwargs):
        self.calls += 1
        return ModelResult(self.status, self.intent, {})


def request(query="喜剧，两个小时以内", **extra):
    return RecommendationRequest(mode="discover", query=query, session_id="offline", input_source="natural_language", **extra)


def test_model_tool_selection_and_refinement_form_a_real_graph_path():
    catalog = Catalog()
    model = Model(IntentDecision(updates={"genres": ["喜剧"], "max_runtime_minutes": 120}))
    flow = AgentWorkflow(catalog, lambda: model)
    first = flow.run(request())
    assert first.status == "ready" and first.method == "llm-v1"
    assert len(first.candidates) == 3 and catalog.calls == 1
    model.intent = IntentDecision(action="refine", updates={"max_runtime_minutes": 90})
    second = flow.run(request("改成90分钟以内"), first.context)
    assert second.constraints.genres == ["喜剧"]
    assert second.constraints.max_runtime_minutes == 90
    assert all(row[0].runtime_minutes <= 90 for row in second.candidates)
    assert first.context.constraints.max_runtime_minutes == 120


def test_confirmation_skips_catalog_and_resume_does_not_call_model_again():
    catalog = Catalog()
    model = Model(IntentDecision(updates={"genres": ["恐怖"], "exclude_genres": ["恐怖"]}, conflicts=["类型矛盾"]))
    flow = AgentWorkflow(catalog, lambda: model)
    body = request("想看恐怖片，但不要恐怖片")
    first = flow.run(body)
    assert first.status == "needs_clarification" and catalog.calls == 0
    assert not first.candidates
    question = first.questions[0]
    confirmed = RecommendationRequest.model_validate({**body.model_dump(), "clarification": {
        "clarification_id": first.clarification_id,
        "answers": [{"question_id": question.question_id, "option": question.options[1]}]}})
    result = flow.run(confirmed, first.context)
    assert result.status == "ready" and model.calls == 1 and catalog.calls == 1
    assert result.constraints.exclude_genres == ["恐怖"]
    assert all("恐怖" not in row[0].genres for row in result.candidates)

    # The browser may cancel after the server completed but before receiving it.
    retried = flow.run(confirmed, result.context)
    assert retried.status == "ready" and model.calls == 1
    assert retried.constraints == result.constraints
    changed = confirmed.model_copy(update={"query": "改为喜剧"})
    assert flow.run(changed, retried.context).error_code == "STALE_CLARIFICATION"
    newer = flow.run(request("新的选片想法"), retried.context)
    assert flow.run(confirmed, newer.context).error_code == "STALE_CLARIFICATION"


def test_reroll_and_reset_skip_model_and_do_not_share_other_context():
    catalog = Catalog()
    model = Model(IntentDecision(updates={"genres": ["喜剧"]}))
    flow = AgentWorkflow(catalog, lambda: model)
    first = flow.run(request())
    second = flow.run(request("换一组"), first.context)
    assert second.status == "empty" and model.calls == 1
    assert set(second.constraints.exclude_movie_ids) == {"itunes:1", "itunes:2", "itunes:3"}
    reset = flow.run(request("重新开始"), second.context)
    assert reset.constraints == Constraints() and model.calls == 1
    assert AgentContext().constraints == Constraints()


def test_structured_path_and_model_failure_have_terminal_states():
    catalog = Catalog()
    model = Model(status="timeout")
    flow = AgentWorkflow(catalog, lambda: model)
    failed = flow.run(request())
    assert failed.status == "error" and failed.error_code == "MODEL_TIMEOUT"
    assert catalog.calls == 0
    body = request("随意探索").model_copy(update={"input_source": "structured"})
    ready = flow.run(body)
    assert ready.status == "ready" and ready.method == "rules-v1"
    assert model.calls == 1 and catalog.calls == 1


def test_unsupported_requirement_must_be_explicitly_confirmed():
    catalog = Catalog()
    model = Model(IntentDecision(updates={"genres": ["喜剧"]}, unhandled=["豆瓣9分以上"]))
    result = AgentWorkflow(catalog, lambda: model).run(request("豆瓣9分以上的喜剧"))
    assert result.status == "needs_clarification" and catalog.calls == 0
    assert result.questions[0].question_id == "unhandled"


def test_dismissal_can_be_undone_without_losing_reroll_history():
    catalog = Catalog()
    model = Model(IntentDecision(updates={"genres": ["喜剧"]}))
    flow = AgentWorkflow(catalog, lambda: model)
    first = flow.run(request())
    model.intent = IntentDecision(action="refine")
    hidden = flow.run(request("保持条件", constraints={"exclude_movie_ids": ["itunes:1"]}), first.context)
    assert "itunes:1" not in {m.movie_id for m, _ in hidden.candidates}
    undone = flow.run(request("保持条件", constraints={"exclude_movie_ids": []}), hidden.context)
    assert "itunes:1" in {m.movie_id for m, _ in undone.candidates}
    rerolled = flow.run(request("换一组"), undone.context)
    continued = flow.run(request("保持条件", constraints={"exclude_movie_ids": []}), rerolled.context)
    assert continued.candidates == []
