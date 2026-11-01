"""Persistent anonymous memory; every movie used here is an offline double."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from app.services.storage import Repository, StoreError
from scripts.movie_server import create_app
from tests.test_movie_intent import CatalogDouble


def test_same_origin_api_preserves_identity_memory_and_no_store_headers(tmp_path):
    repo = Repository(tmp_path / "merged.sqlite3")
    with TestClient(create_app(CatalogDouble(), repository=repo)) as client:
        identity = client.post("/api/identities")
        assert identity.status_code == 200
        assert identity.headers["cache-control"] == "no-store"
        headers = {"Authorization": "Bearer " + identity.json()["identity_token"]}
        session = client.post("/api/sessions", headers=headers)
        assert session.headers["cache-control"] == "no-store"
        preferences = client.get("/api/me/preferences", headers=headers)
        assert preferences.status_code == 200
        assert preferences.headers["cache-control"] == "no-store"
        seen = client.get("/api/me/seen", headers=headers)
        assert seen.status_code == 200 and seen.json()["movie_ids"] == []
        assert client.get("/api/health").json()["capabilities"]["long_term_memory"] is True
        assert client.get("/api/configuration").status_code == 200
        removed = client.delete("/api/me/data?confirmed=true", headers=headers)
        assert removed.status_code == 200
        assert client.get("/api/me/preferences", headers=headers).status_code == 401


def test_migration_restart_isolation_and_expiring_sessions(tmp_path):
    path = tmp_path / "state.sqlite3"
    repo = Repository(path, clock=lambda: 100)
    token, owner = repo.create_identity()
    other_token, other = repo.create_identity()
    repo.create_session("a" * 32, owner, 10)
    repo.save_preferences(owner, {"genres": ["喜剧"]}, enabled=True, expected_version=0)
    repo.close()
    reopened = Repository(path, clock=lambda: 105)
    assert reopened.authenticate(token) == owner
    assert reopened.preferences(owner)["constraints"]["genres"] == ["喜剧"]
    assert reopened.preferences(other)["constraints"]["genres"] == []
    assert reopened.session("a" * 32, owner)["expires_at"] == 110
    with pytest.raises(StoreError):
        reopened.session("a" * 32, other)
    expired = Repository(path, clock=lambda: 111)
    with pytest.raises(StoreError):
        expired.session("a" * 32, owner)
    assert reopened.authenticate(other_token) == other


def test_feedback_atomic_idempotency_conflict_and_undo(tmp_path):
    repo = Repository(tmp_path / "state.sqlite3")
    _, owner = repo.create_identity()
    repo.create_session("s", owner, 60)
    payload = dict(event_id="event-1", session_id="s", movie_id="itunes:101", action="seen", confirmed=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repo.feedback(owner, payload), range(4)))
    assert len({r["version"] for r in results}) == 1
    assert repo.seen(owner) == ["itunes:101"]
    with pytest.raises(StoreError) as error:
        repo.feedback(owner, {**payload, "action": "unseen"})
    assert error.value.code == "EVENT_CONFLICT"
    repo.feedback(owner, dict(event_id="undo-1", session_id="s", action="undo", target_event_id="event-1"))
    assert repo.seen(owner) == []
    with pytest.raises(StoreError):
        repo.feedback(owner, dict(event_id="undo-2", session_id="s", action="undo", target_event_id="event-1"))


def test_delete_revokes_identity_sessions_and_feedback(tmp_path):
    repo = Repository(tmp_path / "state.sqlite3")
    token, owner = repo.create_identity()
    repo.create_session("s", owner, 60)
    repo.feedback(owner, dict(event_id="e", session_id="s", movie_id="itunes:101", action="dismiss"))
    assert repo.dismissed(owner, "s") == ["itunes:101"]
    repo.delete_identity(owner)
    with pytest.raises(StoreError):
        repo.authenticate(token)
    assert repo.connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    assert repo.connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def setup(tmp_path):
    repo = Repository(tmp_path / "api.sqlite3")
    client = TestClient(create_app(CatalogDouble(), repository=repo))
    identity = client.post("/identities").json()
    headers = {"Authorization": "Bearer " + identity["identity_token"]}
    sid = client.post("/sessions", headers=headers).json()["session_id"]
    return client, repo, headers, sid


def recommendation(sid, enabled=True):
    return dict(mode="discover", query="直接看看", session_id=sid, memory_enabled=enabled,
                constraints={}, input_source="structured")


def test_api_requires_confirmation_and_version_without_silent_memory_write(tmp_path):
    client, repo, headers, sid = setup(tmp_path)
    assert client.get("/me/preferences").status_code == 401
    body = dict(enabled=True, constraints={"genres": ["喜剧"]}, expected_version=0)
    assert client.put("/me/preferences", headers=headers, json=body).status_code == 422
    saved = client.put("/me/preferences", headers=headers, json={**body, "confirmed": True})
    assert saved.status_code == 200 and saved.json()["version"] == 1
    assert client.put("/me/preferences", headers=headers, json={**body, "confirmed": True}).status_code == 409
    temporary = {**body, "expected_version": 1, "confirmed": True, "constraints": {"exclude_movie_ids": ["itunes:101"]}}
    assert client.put("/me/preferences", headers=headers, json=temporary).status_code == 422
    result = client.post("/recommendations", headers=headers, json=recommendation(sid)).json()
    assert result["memory_used"] is True
    assert [c["movie"]["movie_id"] for c in result["candidates"]] == ["itunes:101"]
    # Explicit current picks override saved preferences, including explicit empty lists.
    current = recommendation(sid)
    current["constraints"] = {"genres": ["剧情"]}
    assert client.post("/recommendations", headers=headers, json=current).json()["candidates"][0]["movie"]["movie_id"] == "itunes:102"
    assert len(client.post("/recommendations", headers=headers, json=recommendation(sid, False)).json()["candidates"]) == 3


def test_seen_persists_across_sessions_dismissal_does_not_and_undo_recovers(tmp_path):
    client, repo, headers, sid = setup(tmp_path)
    client.put("/me/preferences", headers=headers, json=dict(enabled=True, constraints={}, confirmed=True, expected_version=0))
    seen = dict(event_id="seen-1", session_id=sid, action="seen", movie_id="itunes:101", confirmed=True)
    assert client.post("/feedback", headers=headers, json=seen).status_code == 200
    assert client.post("/feedback", headers=headers, json=seen).status_code == 200
    new_sid = client.post("/sessions", headers=headers).json()["session_id"]
    result = client.post("/recommendations", headers=headers, json=recommendation(new_sid)).json()
    assert "itunes:101" not in [c["movie"]["movie_id"] for c in result["candidates"]]
    dismiss = dict(event_id="dismiss-1", session_id=new_sid, action="dismiss", movie_id="itunes:102")
    assert client.post("/feedback", headers=headers, json=dismiss).status_code == 200
    assert client.get("/me/seen", headers=headers).json()["movie_ids"] == ["itunes:101"]
    undo = dict(event_id="undo-1", session_id=new_sid, action="undo", target_event_id="dismiss-1")
    assert client.post("/feedback", headers=headers, json=undo).status_code == 200
    assert client.post("/recommendations", headers=headers, json=recommendation(new_sid)).json()["matched_count"] == 3


def test_owned_session_cannot_be_used_anonymously_and_delete_never_resurrects(tmp_path):
    client, repo, headers, sid = setup(tmp_path)
    assert client.post("/recommendations", json=recommendation(sid, False)).status_code == 403
    assert client.delete("/me/data", headers=headers).status_code == 422
    assert client.delete("/me/data?confirmed=true", headers=headers).status_code == 200
    assert client.get("/me/preferences", headers=headers).status_code == 401
    assert client.post("/recommendations", json=recommendation(sid)).status_code in (401, 409)


def test_backup_restore_and_version_conflict_rollback(tmp_path):
    repo = Repository(tmp_path / "original.sqlite3")
    token, owner = repo.create_identity()
    repo.save_preferences(owner, {"moods": ["轻松解压"]}, enabled=True, expected_version=0)
    with pytest.raises(StoreError):
        repo.save_preferences(owner, {}, enabled=False, expected_version=0)
    target = tmp_path / "backup.sqlite3"
    repo.backup(target)
    restored = Repository(target)
    assert restored.authenticate(token) == owner
    assert restored.preferences(owner)["enabled"] is True
    assert restored.preferences(owner)["version"] == 1


def test_existing_v1_database_migrates_without_losing_private_state(tmp_path):
    path = tmp_path / "v1.sqlite3"
    repo = Repository(path)
    token, owner = repo.create_identity()
    repo.save_preferences(owner, {"genres": ["喜剧"]}, enabled=True, expected_version=0)
    # Simulate an existing v1 deployment, before evidence/mapping tables existed.
    with repo.transaction() as db:
        db.execute("DROP TABLE evidence_cache")
        db.execute("DROP TABLE external_identities")
        db.execute("PRAGMA user_version=1")
    repo.close()
    reopened = Repository(path)
    assert reopened.connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert reopened.authenticate(token) == owner
    assert reopened.preferences(owner)["constraints"]["genres"] == ["喜剧"]
    assert reopened.cache_get("itunes:1", "Douban", "1") is None
    assert reopened.mappings("itunes:1") == []


def test_model_followup_and_preference_deletion_do_not_resurrect_memory(tmp_path):
    from scripts.mvp_intent_contracts import IntentDecision
    from tests.test_mvp_workflow import Catalog, Model
    repo = Repository(tmp_path / "agent.sqlite3")
    model = Model(IntentDecision(updates={"max_runtime_minutes": 120}))
    catalog = Catalog()
    catalog.fetch_count = 0
    client = TestClient(create_app(catalog, repository=repo, model_factory=lambda: model))
    identity = client.post("/identities").json()
    headers = {"Authorization": "Bearer " + identity["identity_token"]}
    sid = client.post("/sessions", headers=headers).json()["session_id"]
    client.put("/me/preferences", headers=headers, json=dict(enabled=True, constraints={"exclude_genres": ["恐怖"]}, expected_version=0, confirmed=True))
    body = {**recommendation(sid), "input_source": "natural_language", "query": "120分钟以内"}
    first = client.post("/recommendations", headers=headers, json=body).json()
    assert first["memory_used"] is True
    assert first["interpretation"]["effective_constraints"]["exclude_genres"] == ["恐怖"]
    client.delete("/me/preferences?expected_version=1&confirmed=true", headers=headers)
    model.intent = IntentDecision(action="refine", updates={"max_runtime_minutes": 90})
    second = client.post("/recommendations", headers=headers, json={**body, "query": "改成90分钟"}).json()
    assert second["memory_used"] is False
    assert second["interpretation"]["effective_constraints"]["exclude_genres"] == []


def test_second_identity_cannot_read_or_change_first_identity_session(tmp_path):
    client, repo, headers, sid = setup(tmp_path)
    token = client.post("/identities").json()["identity_token"]
    other = {"Authorization": "Bearer " + token}
    assert client.post("/feedback", headers=other, json=dict(session_id=sid, event_id="wrong", action="dismiss", movie_id="itunes:101")).status_code == 403
    assert client.post("/recommendations", headers=other, json=recommendation(sid)).status_code == 403
    assert client.get("/me/seen", headers=other).json()["movie_ids"] == []


def test_inflight_memory_change_rejects_old_result_and_clears_saved_context(tmp_path):
    from scripts.mvp_intent_contracts import IntentDecision
    from tests.test_mvp_workflow import Catalog, Model
    repo = Repository(tmp_path / "race.sqlite3")
    token, owner = repo.create_identity()
    repo.save_preferences(owner, {"genres": ["喜剧"]}, enabled=True, expected_version=0)
    class ChangingCatalog(Catalog):
        def pool(self, genres):
            repo.save_preferences(owner, {}, enabled=False, expected_version=1)
            return super().pool(genres)
    catalog = ChangingCatalog()
    catalog.fetch_count = 0
    client = TestClient(create_app(catalog, repository=repo, model_factory=lambda: Model(IntentDecision())))
    headers = {"Authorization": "Bearer " + token}
    sid = client.post("/sessions", headers=headers).json()["session_id"]
    body = {**recommendation(sid), "input_source": "natural_language", "query": "看电影"}
    assert client.post("/recommendations", headers=headers, json=body).status_code == 409


def test_current_explicit_empty_model_update_overrides_saved_genres(tmp_path):
    from scripts.mvp_intent_contracts import IntentDecision
    from tests.test_mvp_workflow import Catalog, Model
    repo = Repository(tmp_path / "clear.sqlite3")
    model = Model(IntentDecision(updates={"genres": []}))
    catalog = Catalog()
    catalog.fetch_count = 0
    client = TestClient(create_app(catalog, repository=repo, model_factory=lambda: model))
    token = client.post("/identities").json()["identity_token"]
    headers = {"Authorization": "Bearer " + token}
    sid = client.post("/sessions", headers=headers).json()["session_id"]
    client.put("/me/preferences", headers=headers, json=dict(enabled=True, constraints={"genres": ["喜剧"]}, expected_version=0, confirmed=True))
    body = {**recommendation(sid), "input_source": "natural_language", "query": "这次不限制类型"}
    assert client.post("/recommendations", headers=headers, json=body).json()["interpretation"]["effective_constraints"]["genres"] == []
    model.intent = IntentDecision(action="refine", updates={"max_runtime_minutes": 90})
    followup = client.post("/recommendations", headers=headers, json={**body, "query": "90分钟内"}).json()
    assert followup["interpretation"]["effective_constraints"]["genres"] == []


def test_combined_saved_and_temporary_exclusions_return_controlled_error(tmp_path):
    client, repo, headers, sid = setup(tmp_path)
    owner = repo.authenticate(headers["Authorization"][7:])
    client.put("/me/preferences", headers=headers, json=dict(enabled=True, constraints={}, expected_version=0, confirmed=True))
    with repo.transaction() as db:
        db.executemany("INSERT INTO seen VALUES (?,?)", [(owner, f"itunes:{i}") for i in range(1000, 1400)])
    body = recommendation(sid)
    body["constraints"] = {"exclude_movie_ids": [f"itunes:{i}" for i in range(2000, 2200)]}
    result = client.post("/recommendations", headers=headers, json=body)
    assert result.status_code == 409
    assert result.json()["code"] == "EVENT_CONFLICT"
    assert len(repo.seen(owner)) == 400


def test_failed_evidence_does_not_commit_unseen_agent_context(tmp_path):
    from scripts.mvp_intent_contracts import IntentDecision
    from scripts.movie_catalog_errors import CatalogError
    from tests.test_mvp_workflow import Catalog, Model
    model = Model(IntentDecision(updates={"genres": ["喜剧"]}))
    catalog = Catalog()
    catalog.fetch_count = 0
    class FailingEvidence:
        fail = True
        def collect(self, movie):
            if self.fail:
                raise CatalogError()
            return []
    evidence = FailingEvidence()
    client = TestClient(create_app(catalog, model_factory=lambda: model, evidence_service=evidence))
    sid = client.post("/sessions").json()["session_id"]
    body = {**recommendation(sid, False), "input_source": "natural_language", "query": "喜剧"}
    assert client.post("/recommendations", json=body).status_code == 503
    evidence.fail = False
    model.intent = IntentDecision(action="refine", updates={"max_runtime_minutes": 90})
    result = client.post("/recommendations", json={**body, "query": "90分钟内"}).json()
    assert result["interpretation"]["effective_constraints"]["genres"] == []
