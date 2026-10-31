"""SQLite anonymous identities, opt-in memory and transactional feedback.

Bearer tokens are returned once and stored only as SHA-256 digests. No prose,
model messages or credentials enter the database. Use one local demo process.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
from threading import RLock
import time
from uuid import uuid4

from scripts.movie_catalog_errors import CatalogError
from scripts.s0_contracts import Constraints


class StoreError(CatalogError):
    pass


class Repository:
    def __init__(self, path=":memory:", *, clock=time.time):
        self.path, self.clock, self.lock = str(path), clock, RLock()
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        with self.transaction() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 3:
                raise RuntimeError("Database is newer than this application")
            if version == 0:
                for sql in (
                    "CREATE TABLE identities (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created REAL NOT NULL)",
                    "CREATE TABLE preferences (owner TEXT PRIMARY KEY REFERENCES identities(id) ON DELETE CASCADE, enabled INTEGER NOT NULL DEFAULT 0, constraints_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 0)",
                    "CREATE TABLE sessions (id TEXT PRIMARY KEY, owner TEXT REFERENCES identities(id) ON DELETE CASCADE, expires REAL NOT NULL)",
                    "CREATE TABLE seen (owner TEXT REFERENCES identities(id) ON DELETE CASCADE, movie_id TEXT NOT NULL, PRIMARY KEY(owner,movie_id))",
                    "CREATE TABLE dismissals (session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, movie_id TEXT NOT NULL, PRIMARY KEY(session_id,movie_id))",
                    "CREATE TABLE events (owner TEXT REFERENCES identities(id) ON DELETE CASCADE, event_id TEXT NOT NULL, payload TEXT NOT NULL, result TEXT NOT NULL, session_id TEXT NOT NULL, action TEXT NOT NULL, movie_id TEXT, previous INTEGER, undone INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(owner,event_id))",
                    "CREATE INDEX session_expiry ON sessions(expires)",
                ):
                    db.execute(sql)
                db.execute("PRAGMA user_version=1")
            if version < 2:
                db.execute("CREATE TABLE evidence_cache (movie_id TEXT NOT NULL, source TEXT NOT NULL, external_id TEXT NOT NULL, fetched REAL NOT NULL, result TEXT NOT NULL, PRIMARY KEY(movie_id,source,external_id))")
                db.execute("CREATE TABLE external_identities (movie_id TEXT NOT NULL, provider TEXT NOT NULL, identity_json TEXT NOT NULL, PRIMARY KEY(movie_id,provider))")
                db.execute("PRAGMA user_version=2")
            if version < 3:
                db.execute("CREATE UNIQUE INDEX unique_external_mapping ON external_identities(provider,json_extract(identity_json,'$.external_id'))")
                db.execute("PRAGMA user_version=3")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.connection.close()

    def backup(self, target):
        target = Path(target).resolve()
        if self.path != ":memory:" and target == Path(self.path).resolve():
            raise ValueError("Backup destination must differ from database")
        if target.exists():
            raise ValueError("Backup destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, sqlite3.connect(target) as destination:
            self.connection.backup(destination)

    def create_identity(self):
        token, owner = secrets.token_urlsafe(32), uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO identities VALUES (?,?,?)", (owner, sha256(token.encode()).hexdigest(), self.clock()))
            db.execute("INSERT INTO preferences(owner) VALUES (?)", (owner,))
        return token, owner

    def authenticate(self, token):
        with self.lock:
            row = self.connection.execute("SELECT id FROM identities WHERE token_hash=?", (sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise StoreError("IDENTITY_REQUIRED", "匿名身份无效或已删除，请重新建立。", 401)
        return row[0]

    def authenticate_authorized_owner(self, owner):
        with self.lock:
            found = self.connection.execute("SELECT 1 FROM identities WHERE id=?", (owner,)).fetchone()
        if not found:
            raise StoreError("IDENTITY_REQUIRED", "匿名身份已删除，请重新建立。", 401)

    def create_session(self, sid, owner, ttl):
        with self.transaction() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (self.clock(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, owner, self.clock() + ttl))

    def session(self, sid, owner):
        with self.lock:
            row = self.connection.execute("SELECT owner,expires FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row or row["expires"] <= self.clock():
            raise StoreError("SESSION_EXPIRED", "本次会话已过期，请重新开始。", 409)
        if row["owner"] != owner:
            raise StoreError("IDENTITY_MISMATCH", "此会话不属于当前匿名身份。", 403)
        return {"owner": row["owner"], "expires_at": row["expires"]}

    def preferences(self, owner):
        with self.lock:
            row = self.connection.execute("SELECT * FROM preferences WHERE owner=?", (owner,)).fetchone()
        if row is None:
            raise StoreError("IDENTITY_REQUIRED", "匿名身份不存在。", 401)
        return {"enabled": bool(row["enabled"]), "constraints": Constraints.model_validate_json(row["constraints_json"]).model_dump(), "version": row["version"]}

    def save_preferences(self, owner, constraints, *, enabled, expected_version):
        data = Constraints.model_validate(constraints).model_dump_json()
        with self.transaction() as db:
            result = db.execute("UPDATE preferences SET enabled=?, constraints_json=?, version=version+1 WHERE owner=? AND version=?", (enabled, data, owner, expected_version))
            if result.rowcount != 1:
                raise StoreError("VERSION_CONFLICT", "偏好已变化，请刷新后重新确认。", 409)
        return self.preferences(owner)

    def seen(self, owner):
        with self.lock:
            return [r[0] for r in self.connection.execute("SELECT movie_id FROM seen WHERE owner=? ORDER BY movie_id", (owner,))]

    def dismissed(self, owner, sid):
        self.session(sid, owner)
        with self.lock:
            return [r[0] for r in self.connection.execute("SELECT movie_id FROM dismissals WHERE session_id=? ORDER BY movie_id", (sid,))]

    def feedback(self, owner, payload):
        sid, event_id, action = payload["session_id"], payload["event_id"], payload["action"]
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.transaction() as db:
            self.session(sid, owner)
            existing = db.execute("SELECT payload,result FROM events WHERE owner=? AND event_id=?", (owner, event_id)).fetchone()
            if existing:
                if existing["payload"] != data:
                    raise StoreError("EVENT_CONFLICT", "相同事件编号已用于其他操作。", 409)
                return json.loads(existing["result"])
            movie_id, previous = payload.get("movie_id"), None
            if action == "undo":
                original = db.execute("SELECT * FROM events WHERE owner=? AND event_id=?", (owner, payload.get("target_event_id"))).fetchone()
                if not original or original["undone"] or original["action"] == "undo":
                    raise StoreError("EVENT_CONFLICT", "此操作不存在或已撤销。", 409)
                if original["action"] in {"dismiss", "restore"} and original["session_id"] != sid:
                    raise StoreError("EVENT_CONFLICT", "临时操作只能在原会话撤销。", 409)
                # Do not undo over a newer edit of the same state.
                rowid = db.execute("SELECT rowid FROM events WHERE owner=? AND event_id=?", (owner, original["event_id"])).fetchone()[0]
                actions = ('seen', 'unseen') if original["action"] in {'seen', 'unseen'} else ('dismiss', 'restore')
                newer = db.execute("SELECT 1 FROM events WHERE owner=? AND movie_id=? AND rowid>? AND undone=0 AND action IN (?,?) AND (action IN ('seen','unseen') OR session_id=?) LIMIT 1", (owner, original["movie_id"], rowid, *actions, sid)).fetchone()
                if newer:
                    raise StoreError("EVENT_CONFLICT", "后续操作已改变此影片状态，请直接修改当前状态。", 409)
                movie_id = original["movie_id"]
                self._set_state(db, owner, sid, movie_id, original["action"], bool(original["previous"]))
                db.execute("UPDATE events SET undone=1 WHERE owner=? AND event_id=?", (owner, original["event_id"]))
            else:
                if action not in {"seen", "unseen", "dismiss", "restore"} or not movie_id:
                    raise StoreError("EVENT_CONFLICT", "无效反馈。", 422)
                if action in {"seen", "unseen"} and not payload.get("confirmed"):
                    raise StoreError("CONSENT_REQUIRED", "修改长期已看记录需要明确确认。", 422)
                table, key = ("seen", owner) if action in {"seen", "unseen"} else ("dismissals", sid)
                column = "owner" if table == "seen" else "session_id"
                previous = db.execute(f"SELECT 1 FROM {table} WHERE {column}=? AND movie_id=?", (key, movie_id)).fetchone() is not None
                if not previous and action in {"seen", "dismiss"} and db.execute(f"SELECT count(*) FROM {table} WHERE {column}=?", (key,)).fetchone()[0] >= 400:
                    raise StoreError("EVENT_CONFLICT", "记录已达到本机演示上限，请清理后再保存。", 409)
                self._set_state(db, owner, sid, movie_id, action, action in {"seen", "dismiss"})
            db.execute("UPDATE preferences SET version=version+1 WHERE owner=?", (owner,))
            version = db.execute("SELECT version FROM preferences WHERE owner=?", (owner,)).fetchone()[0]
            result = {"event_id": event_id, "version": version, "action": action, "movie_id": movie_id}
            db.execute("INSERT INTO events(owner,event_id,payload,result,session_id,action,movie_id,previous) VALUES (?,?,?,?,?,?,?,?)", (owner, event_id, data, json.dumps(result), sid, action, movie_id, previous))
        return result

    @staticmethod
    def _set_state(db, owner, sid, movie_id, action, present):
        table, column, key = ("seen", "owner", owner) if action in {"seen", "unseen"} else ("dismissals", "session_id", sid)
        if present:
            db.execute(f"INSERT OR IGNORE INTO {table} VALUES (?,?)", (key, movie_id))
        else:
            db.execute(f"DELETE FROM {table} WHERE {column}=? AND movie_id=?", (key, movie_id))

    def delete_seen(self, owner):
        with self.transaction() as db:
            db.execute("DELETE FROM seen WHERE owner=?", (owner,))
            db.execute("DELETE FROM events WHERE owner=? AND action IN ('seen','unseen','undo')", (owner,))
            db.execute("UPDATE preferences SET version=version+1 WHERE owner=?", (owner,))

    def delete_identity(self, owner):
        with self.transaction() as db:
            db.execute("DELETE FROM identities WHERE id=?", (owner,))

    def cache_get(self, movie_id, source, external_id):
        with self.lock:
            row = self.connection.execute("SELECT fetched,result FROM evidence_cache WHERE movie_id=? AND source=? AND external_id=?", (movie_id, source, external_id)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def cache_put(self, movie_id, source, external_id, fetched, result):
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO evidence_cache VALUES (?,?,?,?,?)", (movie_id, source, external_id, fetched, json.dumps(result)))
            db.execute("DELETE FROM evidence_cache WHERE rowid IN (SELECT rowid FROM evidence_cache ORDER BY fetched DESC LIMIT -1 OFFSET 1000)")

    def register_mapping(self, movie_id, identity):
        from scripts.movie_identity import confirm_external_identity
        from scripts.s0_contracts import Movie
        with self.transaction() as db:
            existing = self.mappings(movie_id)
            confirm_external_identity(Movie(movie_id=movie_id, title="Mapping validation", external_ids=existing), identity)
            conflict = db.execute("SELECT movie_id FROM external_identities WHERE provider=? AND json_extract(identity_json,'$.external_id')=? AND movie_id!=?", (identity.provider, identity.external_id, movie_id)).fetchone()
            if conflict:
                raise ValueError("external identity already belongs to another canonical movie")
            db.execute("INSERT OR REPLACE INTO external_identities VALUES (?,?,?)", (movie_id, identity.provider, identity.model_dump_json()))

    def mappings(self, movie_id):
        from scripts.s0_contracts import ExternalMovieIdentity
        with self.lock:
            return [ExternalMovieIdentity.model_validate_json(r[0]) for r in self.connection.execute("SELECT identity_json FROM external_identities WHERE movie_id=?", (movie_id,))]
