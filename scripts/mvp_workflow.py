"""M05 request-level LangGraph. Context is explicit and owned by the caller."""
from dataclasses import dataclass, field, replace
import hashlib
import json
import time
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from scripts.movie_catalog import CatalogError, MOODS
from scripts.mvp_intent_contracts import IntentDecision, TurnContext
from scripts.mvp_recommendation_rules import merge_conditions, select_movies
from scripts.s0_contracts import Constraints, Question, RecommendationRequest


@dataclass
class PendingConfirmation:
    token: str
    fingerprint: str
    questions: list
    alternatives: dict
    constraints: Constraints
    unhandled: list
    method: str


@dataclass
class AgentContext:
    constraints: Constraints = field(default_factory=Constraints)
    displayed: list[str] = field(default_factory=list)
    has_previous: bool = False
    method: str = "rules-v1"
    pending: PendingConfirmation | None = None
    reroll_excluded: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    status: str
    constraints: Constraints
    context: AgentContext
    method: str = "rules-v1"
    candidates: list = field(default_factory=list)
    catalog_size: int = 0
    matched_count: int = 0
    questions: list = field(default_factory=list)
    clarification_id: str | None = None
    unhandled: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    error_code: str | None = None


class GraphState(TypedDict, total=False):
    body: RecommendationRequest
    context: AgentContext
    intent: IntentDecision
    method: str
    constraints: Constraints
    unhandled: list
    confirmed: bool
    deadline: float
    result: WorkflowResult


def fingerprint(body):
    values = body.model_dump(exclude={"clarification", "clarification_count"})
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class AgentWorkflow:
    def __init__(self, catalog, model_factory):
        self.catalog, self.model_factory = catalog, model_factory
        graph = StateGraph(GraphState)
        graph.add_node("understand", self._understand)
        graph.add_node("resolve", self._resolve)
        graph.add_node("catalog", self._catalog)
        graph.add_edge(START, "understand")
        graph.add_conditional_edges("understand", lambda s: END if "result" in s else "resolve")
        graph.add_conditional_edges("resolve", lambda s: END if "result" in s else "catalog")
        graph.add_edge("catalog", END)
        self.graph = graph.compile()

    def run(self, body, context=None):
        state = self.graph.invoke({"body": body, "context": context or AgentContext(),
                                   "deadline": time.monotonic() + 60}, {"recursion_limit": 8})
        return state["result"]

    def _error(self, state, code):
        context = state["context"]
        return {"result": WorkflowResult("error", context.constraints.model_copy(deep=True), context,
                                         method=context.method, error_code=code)}

    def _understand(self, state):
        body, context = state["body"], state["context"]
        if body.clarification:
            pending = context.pending
            if not pending or pending.token != body.clarification.clarification_id or pending.fingerprint != fingerprint(body):
                return self._error(state, "STALE_CLARIFICATION")
            answers = {a.question_id: a.option for a in body.clarification.answers}
            if len(answers) != len(body.clarification.answers) or set(answers) != {q.question_id for q in pending.questions} or any(answers[q.question_id] not in q.options for q in pending.questions):
                return self._error(state, "INVALID_CLARIFICATION")
            constraints = pending.alternatives.get(answers.get("conflict"), pending.constraints)
            return {"constraints": constraints, "confirmed": True, "method": pending.method,
                    "unhandled": pending.unhandled, "intent": IntentDecision()}
        query = body.query.strip()
        if query in ("重新开始", "清空选片条件"):
            return {"intent": IntentDecision(action="reset"), "method": "rules-v1"}
        if query in ("换一组", "换一组真实电影"):
            return {"intent": IntentDecision(action="reroll"), "method": context.method}
        if body.input_source == "structured":
            return {"intent": IntentDecision(), "method": "rules-v1"}
        model = self.model_factory()
        if model is None:
            return self._error(state, "MODEL_NOT_CONFIGURED")
        result = model.interpret(query, context=TurnContext(previous_constraints=context.constraints,
                                 displayed_movie_ids=context.displayed), picks=body.constraints)
        if time.monotonic() > state["deadline"]:
            return self._error(state, "WORKFLOW_TIMEOUT")
        if result.status != "ok":
            return self._error(state, "MODEL_" + result.status.upper())
        return {"intent": result.intent, "method": result.metadata.get("method", "llm-v1")}

    def _resolve(self, state):
        if state.get("confirmed"):
            return {}
        body, context, intent = state["body"], state["context"], state["intent"]
        # Frontend serializes default fields too: they are not fresh user picks.
        picks = body.constraints.model_dump(exclude_defaults=True)
        # Client dismissal list is reversible; reroll history is a separate list.
        if "exclude_movie_ids" in body.constraints.model_fields_set:
            picks["exclude_movie_ids"] = list(dict.fromkeys([*context.reroll_excluded, *body.constraints.exclude_movie_ids]))
        selected = Constraints.model_validate(picks)
        previous = context.constraints.model_copy(update={"exclude_movie_ids": list(context.reroll_excluded)})
        resolution = merge_conditions(intent, previous=previous,
                                      selected=selected, displayed=context.displayed)
        constraints = resolution.constraints
        if not resolution.needs_confirmation:
            return {"constraints": constraints, "unhandled": []}
        questions, alternatives = [], {}
        if resolution.conflicts:
            overlap = set(constraints.genres) & set(constraints.exclude_genres)
            if overlap:
                include = constraints.model_copy(update={"exclude_genres": [g for g in constraints.exclude_genres if g not in overlap]})
                exclude = constraints.model_copy(update={"genres": [g for g in constraints.genres if g not in overlap]})
                alternatives = {"保留想看的类型": include, "排除这些类型": exclude}
                text = "这些类型同时被选择和排除：" + "、".join(sorted(overlap)) + "，这次如何处理？"
            else:
                picks = merge_conditions(IntentDecision(action=intent.action), previous=context.constraints,
                                         selected=body.constraints, displayed=context.displayed).constraints
                alternatives = {"按文字条件": constraints, "按点选条件": picks}
                text = "文字与本次点选条件有冲突，这次以哪组为准？"
            questions.append(Question(question_id="conflict", text=text, options=list(alternatives)))
        if resolution.unhandled:
            questions.append(Question(question_id="unhandled", text="暂时无法执行：" + "；".join(resolution.unhandled) + "。要仅按已识别条件继续吗？", options=["仅按已识别条件继续"]))
        pending = PendingConfirmation(uuid4().hex, fingerprint(body), questions, alternatives, constraints,
                                      resolution.unhandled, state["method"])
        next_context = replace(context, pending=pending)
        result = WorkflowResult("needs_clarification", constraints, next_context, method=state["method"],
                                questions=questions, clarification_id=pending.token,
                                unhandled=resolution.unhandled, conflicts=resolution.conflicts)
        return {"result": result}

    def _catalog(self, state):
        if time.monotonic() > state["deadline"]:
            return self._error(state, "WORKFLOW_TIMEOUT")
        body, context, constraints = state["body"], state["context"], state["constraints"]
        # LLM calls finish before this lock; reuse provider caching and rate limits.
        with self.catalog.lock:
            if body.mode in ("known_movie", "watchlist"):
                ids = [body.movie_id] if body.mode == "known_movie" else list(dict.fromkeys(body.watchlist_movie_ids))
                if any(not mid.startswith("itunes:") for mid in ids):
                    raise CatalogError("NOT_FOUND", "影片不在当前真实片库中，请重新查找。", 404)
                rows = self.catalog.lookup([mid.removeprefix("itunes:") for mid in ids])
            else:
                mood_genres = set().union(*(MOODS[m] for m in constraints.moods)) if constraints.moods else set()
                genres = constraints.genres or sorted(mood_genres) or (["家庭"] if constraints.company == "和家人" else [])
                rows = self.catalog.pool(genres)
        if time.monotonic() > state["deadline"]:
            return self._error(state, "WORKFLOW_TIMEOUT")
        selection = select_movies(rows, constraints)
        displayed = [] if state["intent"].action == "reset" else context.displayed
        reroll_excluded = [] if state["intent"].action == "reset" else list(context.reroll_excluded)
        if state["intent"].action == "reroll":
            reroll_excluded = list(dict.fromkeys([*reroll_excluded, *context.displayed]))
        next_context = AgentContext(constraints.model_copy(deep=True),
                                    list(dict.fromkeys([*displayed, *(m.movie_id for m, at in selection.candidates)])),
                                    True, state["method"],
                                    # A completed response may never reach a cancelled browser request.
                                    # Keep its fingerprint-bound confirmation valid until the next turn.
                                    pending=context.pending if state.get("confirmed") else None,
                                    reroll_excluded=reroll_excluded)
        return {"result": WorkflowResult("ready" if selection.candidates else "empty", constraints, next_context,
                                         method=state["method"], candidates=selection.candidates,
                                         catalog_size=len(rows), matched_count=len(selection.eligible),
                                         unhandled=state.get("unhandled", []))}
