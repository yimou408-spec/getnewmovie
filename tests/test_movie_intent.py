"""P02 offline behavior tests. The four invented films are test doubles only."""
from threading import RLock

from fastapi.testclient import TestClient

from scripts.movie_server import create_app
from scripts.s0_contracts import Movie


class CatalogDouble:
    def __init__(self):
        self.lock, self.fetch_count, self.calls = RLock(), 0, 0

    def pool(self, genres):
        self.calls += 1
        return [(Movie(movie_id=f"itunes:{i}", title=f"Offline {genre}",
                       genres=[genre], runtime_minutes=runtime, year=2024, tags=tags),
                 "2026-10-22T00:00:00Z") for i, genre, runtime, tags in [
            (101, "喜剧", 90, ["幽默"]), (102, "剧情", 120, ["成长"]),
            (103, "家庭", 80, ["友谊"]), (104, "恐怖", 95, ["恐怖线索"])]]


def setup():
    catalog = CatalogDouble()
    client = TestClient(create_app(catalog))
    sid = client.post("/sessions").json()["session_id"]
    return client, catalog, sid


def request(sid, query, **extra):
    return dict(mode="discover", query=query, session_id=sid,
                input_source="natural_language", **extra)


def answer(client, body, response, choices):
    return client.post("/recommendations", json={**body, "clarification": {
        "clarification_id": response["clarification_id"],
        "answers": [{"question_id": q["question_id"], "option": choice}
                    for q, choice in zip(response["questions"], choices)]}})


def test_natural_text_changes_real_rule_constraints_and_hard_exclusions():
    c, catalog, sid = setup()
    result = c.post("/recommendations", json=request(sid, "想看喜剧，最多一个半小时，不要恐怖片")).json()
    assert result["status"] == "ready"
    effective = result["interpretation"]["effective_constraints"]
    assert effective["genres"] == ["喜剧"]
    assert effective["exclude_genres"] == ["恐怖"]
    assert effective["max_runtime_minutes"] == 90
    assert [x["movie"]["movie_id"] for x in result["candidates"]] == ["itunes:101"]
    assert catalog.calls == 1


def test_text_pick_conflict_requires_explicit_choice_before_catalog_call():
    c, catalog, sid = setup()
    body = request(sid, "看剧情片，120分钟以内", constraints={"genres": ["喜剧"], "max_runtime_minutes": 90})
    pending = c.post("/recommendations", json=body).json()
    assert pending["status"] == "needs_clarification"
    assert pending["candidates"] == [] and catalog.calls == 0
    assert pending["interpretation"]["conflicts"]
    resolved = answer(c, body, pending, ["按文字条件"]).json()
    assert [x["movie"]["movie_id"] for x in resolved["candidates"]] == ["itunes:102"]
    assert answer(c, body, pending, ["按文字条件"]).json()["status"] == "ready"


def test_unknown_condition_is_not_silently_dropped():
    c, catalog, sid = setup()
    body = request(sid, "豆瓣8分以上的喜剧，90分钟以内")
    pending = c.post("/recommendations", json=body).json()
    assert pending["status"] == "needs_clarification" and catalog.calls == 0
    assert "豆瓣" in "".join(pending["interpretation"]["unhandled"])
    resolved = answer(c, body, pending, ["仅按已识别条件继续"]).json()
    assert resolved["status"] == "ready"
    assert any("未采用" in s for s in resolved["warnings"])


def test_session_binding_and_changed_query_reject_stale_answers():
    c, _, sid = setup()
    body = request(sid, "豆瓣8分以上的喜剧")
    pending = c.post("/recommendations", json=body).json()
    second = c.post("/sessions").json()["session_id"]
    assert second != sid
    assert answer(c, {**body, "session_id": second}, pending, ["仅按已识别条件继续"]).status_code == 409
    assert answer(c, {**body, "query": "不要喜剧"}, pending, ["仅按已识别条件继续"]).status_code == 409
    assert answer(c, body, pending, ["invented choice"]).status_code == 422


def test_soft_mood_never_overrides_explicit_genre_and_negation_is_preserved():
    c, _, sid = setup()
    r = c.post("/recommendations", json=request(sid, "想看温暖治愈的喜剧，不要恐怖片，两个小时以内")).json()
    assert r["status"] == "ready"
    assert r["interpretation"]["soft_preferences"]
    assert r["interpretation"]["effective_constraints"]["max_runtime_minutes"] == 120
    assert all(x["movie"]["genres"] == ["喜剧"] for x in r["candidates"])


def test_unrecognized_or_ambiguous_duration_cannot_return_unfiltered_movies():
    c, catalog, sid = setup()
    for text in ["像诺兰但不要太沉重", "90到120分钟的喜剧", "不要超过两小时的喜剧"]:
        r = c.post("/recommendations", json=request(sid, text)).json()
        if text == "不要超过两小时的喜剧":
            assert r["interpretation"]["effective_constraints"]["max_runtime_minutes"] == 120
        else:
            assert r["status"] == "needs_clarification" and not r["candidates"]


def test_legacy_structured_requests_do_not_require_a_server_session():
    c = TestClient(create_app(CatalogDouble()))
    assert c.post("/recommendations", json={"mode": "discover", "query": "no input", "session_id": "legacy"}).status_code == 200
    assert c.post("/recommendations", json=request("unknown", "喜剧")).status_code == 409


def test_confirmed_reroll_extends_exclusions_without_losing_confirmed_choice():
    c, _, sid = setup()
    body = request(sid, "剧情片", constraints={"genres": ["喜剧"]})
    pending = c.post("/recommendations", json=body).json()
    reroll = {**body, "constraints": {**body["constraints"], "exclude_movie_ids": ["itunes:102"]}}
    r = answer(c, reroll, pending, ["按文字条件"]).json()
    assert r["status"] == "empty" and not r["candidates"]
    assert r["interpretation"]["effective_constraints"]["genres"] == ["剧情"]


def test_session_ttl_and_capacity_are_bounded():
    from scripts.movie_intent import IntentSessions
    from scripts.movie_catalog import CatalogError
    from scripts.s0_contracts import RecommendationRequest
    import pytest
    now = [0]
    sessions = IntentSessions(ttl=10, capacity=1, clock=lambda: now[0])
    first = sessions.create()
    second = sessions.create()
    for sid in [first, second]:
        if sid == second:
            now[0] = 11
        with pytest.raises(CatalogError, match="临时会话已过期"):
            sessions.resolve(RecommendationRequest(**request(sid, "喜剧")))


def test_company_is_not_misread_as_genre_and_negated_context_is_not_applied():
    from scripts.movie_intent import parse_text
    assert parse_text("comedy with family")[0] == {"company": "和家人", "genres": ["喜剧"]}
    parsed, unsupported = parse_text("不要和家人，喜剧片，不要新片")
    assert parsed == {"genres": ["喜剧"]}
    assert unsupported == ["不要和家人", "不要新片"]


def test_conflict_copy_uses_readable_condition_names():
    c, _, sid = setup()
    result = c.post("/recommendations", json=request(sid, "剧情片", constraints={"genres": ["喜剧"]})).json()
    assert result["interpretation"]["conflicts"] == ["类型：点选 喜剧；文字 剧情"]
