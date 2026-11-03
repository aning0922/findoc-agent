"""Lease state machine. Reset work never holds a SQLite write transaction."""
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
import time
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException

from app.demo.config import DemoConfig, verify_password
from app.demo.store import ControlStore


def token_hash(token: str | None) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def reject(status: int, code: str, **extra):
    raise HTTPException(status, {"code": code, "message": code.replace("_", " "), **extra})


class RuntimeManager(Protocol):
    handle: object | None

    async def recover(self): ...
    async def reset(self, generation: int): ...
    async def close(self): ...


class DemoController:
    def __init__(self, config: DemoConfig, manager: RuntimeManager, *, clock=time.time):
        self.config, self.manager, self.clock = config, manager, clock
        self.store = ControlStore(config.control_root)
        # Per-controller fingerprint key; operations never store passwords or raw cookies.
        key_path = config.control_root / "operation.key"
        if not key_path.exists():
            key_path.write_bytes(secrets.token_bytes(32))
            key_path.chmod(0o600)
        self.key = key_path.read_bytes()
        self.reset_task = None
        self.sweeper = None

    async def start(self):
        # Restart never trusts a previously issued lease/PID. Manager must retire verified children.
        with self.store.tx() as db:
            slot = db.execute("SELECT * FROM slot").fetchone()
            dirty = slot["state"] != "available" or slot["generation"] > 0
            db.execute("UPDATE sessions SET revoked='controller_restarted',owner_until=NULL "
                       "WHERE revoked IS NULL")
            db.execute("UPDATE operations SET state='interrupted' WHERE state IN ('pending','ready')")
            db.execute("UPDATE resets SET state='failed',phase='interrupted',error_code='controller_restarted' "
                       "WHERE state='running'")
            db.execute("UPDATE slot SET state='degraded',session_hash=NULL,expires=NULL")
        try:
            await self.manager.recover()
            if dirty:
                self._begin_cleanup()
            else:
                with self.store.tx() as db:
                    db.execute("UPDATE slot SET state='available'")
        except Exception:
            # Do not publish a generation if orphan retirement cannot be proved.
            pass
        self.sweeper = asyncio.create_task(self._sweep_loop())

    async def close(self):
        if self.sweeper:
            self.sweeper.cancel()
            await asyncio.gather(self.sweeper, return_exceptions=True)
        if self.reset_task:
            self.reset_task.cancel()
            await asyncio.gather(self.reset_task, return_exceptions=True)
        await self.manager.close()
        self.store.close()

    def _fingerprint(self, kind, payload):
        encoded = json.dumps([kind, payload], sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self.key, encoded, hashlib.sha256).hexdigest()

    def credentials(self, username, password):
        password_ok = verify_password(password, self.config.password_hash)
        username_ok = hmac.compare_digest(username.encode(), self.config.username.encode())
        if not (password_ok and username_ok):
            reject(401, "invalid_credentials")

    def status(self):
        self.expire()
        with self.store.tx() as db:
            state = db.execute("SELECT state FROM slot").fetchone()[0]
        return {"schema_version": "demo-status-v1", "service_state": {
            "available": "ready", "active": "ready", "resetting": "resetting",
            "degraded": "degraded"}[state], "ttl_minutes": self.config.ttl_minutes,
            "conflict_policy": self.config.conflict_policy}

    def session(self, token):
        self.expire()
        with self.store.tx() as db:
            return self._session(db, token)

    def _session(self, db, token):
        session = db.execute("SELECT * FROM sessions WHERE hash=?", (token_hash(token),)).fetchone()
        slot = db.execute("SELECT * FROM slot").fetchone()
        if session is None:
            reject(401, "unauthenticated")
        if session["expires"] <= self.clock() or session["revoked"] == "expired":
            reject(401, "expired")
        if session["revoked"]:
            reject(401, "taken_over" if session["revoked"] == "taken_over" else "unauthenticated")
        if slot["state"] == "degraded":
            reject(503, "reset_failed")
        if slot["state"] != "active" or slot["session_hash"] != session["hash"]:
            reject(401, "unauthenticated")
        return {"schema_version": "demo-session-v1", "state": "active",
                "expires_at": iso(session["expires"]), "server_now": iso(self.clock()),
                "remaining_seconds": max(0, int(session["expires"] - self.clock())),
                "lease_generation": session["generation"], "seed_version": slot["seed_version"],
                "can_review": bool(session["owner_until"] and session["owner_until"] > self.clock()),
                "owner_elevated_until": iso(session["owner_until"]) if session["owner_until"] and session["owner_until"] > self.clock() else None}

    def login(self, payload, token=None, pending=None):
        self.credentials(payload["username"], payload["password"])
        self.expire()
        fingerprint = self._fingerprint("login", payload)
        with self.store.tx() as db:
            existing = db.execute("SELECT * FROM operations WHERE id=?", (payload["operation_id"],)).fetchone()
            if existing:
                return self._repeat(db, existing, fingerprint, token, pending)
            slot = db.execute("SELECT * FROM slot").fetchone()
            if slot["state"] == "active":
                if slot["session_hash"] == token_hash(token):
                    result = self._session(db, token)
                    db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?, ?,?)", (
                        payload["operation_id"], "login", fingerprint, token_hash(token),
                        slot["generation"], slot["reset_id"], "claimed", slot["expires"], token_hash(token)))
                    return 200, result, None
                reject(423, "occupied", remaining_seconds=max(0, int(slot["expires"] - self.clock())),
                       expires_at=iso(slot["expires"]), lease_generation=slot["generation"],
                       takeover_available=self.config.conflict_policy == "takeover_enabled")
            if slot["state"] == "resetting":
                reject(409, "resetting")
            if slot["state"] == "degraded":
                reject(503, "reset_failed")
            result = self._reserve(db, payload["operation_id"], "login", fingerprint, slot)
        self._launch_reset(result[1]["reset_id"], slot["generation"] + 1)
        return result

    def takeover(self, payload, token=None, pending=None):
        self.credentials(payload["username"], payload["password"])
        if self.config.conflict_policy != "takeover_enabled":
            reject(403, "takeover_disabled")
        if payload["confirm"] is not True or not verify_password(
                payload["owner_password"], self.config.owner_password_hash):
            reject(403, "owner_authorization_required")
        self.expire()
        fingerprint = self._fingerprint("takeover", payload)
        with self.store.tx() as db:
            existing = db.execute("SELECT * FROM operations WHERE id=?", (payload["operation_id"],)).fetchone()
            if existing:
                return self._repeat(db, existing, fingerprint, token, pending)
            slot = db.execute("SELECT * FROM slot").fetchone()
            if slot["state"] != "active" or slot["generation"] != payload["expected_generation"]:
                reject(409, "generation_conflict")
            result = self._reserve(db, payload["operation_id"], "takeover", fingerprint, slot)
        self._launch_reset(result[1]["reset_id"], slot["generation"] + 1)
        return result

    def owner_authorize(self, payload, token):
        self.session(token)
        if not self.config.owner_password_hash or payload["confirm"] is not True or not verify_password(
                payload["owner_password"], self.config.owner_password_hash):
            reject(403, "owner_authorization_required")
        fingerprint = self._fingerprint("owner-authorize", payload)
        with self.store.tx() as db:
            session = self._session(db, token)
            existing = db.execute("SELECT * FROM operations WHERE id=?", (payload["operation_id"],)).fetchone()
            if existing:
                if existing["request_hash"] != fingerprint or existing["owner_hash"] != token_hash(token):
                    reject(409, "operation_conflict")
                # Repeating an operation cannot refresh the five-minute grant.
                if not session["can_review"] or existing["deadline"] <= self.clock():
                    reject(403, "owner_grant_expired")
                until = existing["deadline"]
            else:
                row = db.execute("SELECT expires FROM sessions WHERE hash=?", (token_hash(token),)).fetchone()
                until = min(row["expires"], self.clock() + 300)
                db.execute("UPDATE sessions SET owner_until=? WHERE hash=?", (until, token_hash(token)))
                db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?)", (
                    payload["operation_id"], "owner-authorize", fingerprint, token_hash(token),
                    session["lease_generation"], None, "completed", until, token_hash(token)))
            return {"can_review": True, "owner_elevated_until": iso(until)}

    def capture(self, token, *, owner=False):
        session = self.session(token)
        if owner and not session["can_review"]:
            reject(403, "owner_authorization_required")
        handle = self.manager.handle
        if handle is None or handle.generation != session["lease_generation"]:
            reject(503, "runtime_unavailable")
        return handle

    def fence(self, token, generation):
        session = self.session(token)
        if session["lease_generation"] != generation:
            reject(401, "taken_over")

    def _reserve(self, db, operation_id, kind, fingerprint, slot):
        pending_token, reset_id = secrets.token_urlsafe(32), str(uuid4())
        generation = slot["generation"] + 1
        db.execute("UPDATE sessions SET revoked=?,owner_until=NULL WHERE revoked IS NULL",
                   ("taken_over" if kind == "takeover" else "logged_out",))
        db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,NULL)", (
            operation_id, kind, fingerprint, token_hash(pending_token), generation,
            reset_id, "pending", self.clock() + self.config.pending_seconds))
        self._new_reset(db, reset_id, generation)
        return 202, {"schema_version": "demo-attempt-v1", "state": "pending",
                     "operation_id": operation_id, "reset_id": reset_id, "claimable": False}, pending_token

    def _repeat(self, db, operation, fingerprint, token, pending):
        if not hmac.compare_digest(operation["request_hash"], fingerprint):
            reject(409, "operation_conflict")
        if operation["state"] == "claimed" and operation["session_hash"] == token_hash(token):
            return 200, self._session(db, token), None
        if operation["owner_hash"] != token_hash(pending):
            reject(409, "attempt_cookie_required")
        if operation["state"] not in ("pending", "ready"):
            reject(409, "attempt_unavailable")
        return 202, self._operation(operation), None

    def _operation(self, row):
        state = row["state"]
        if state in ("expired", "interrupted"):
            state = "cancelled"
        return {"schema_version": "demo-attempt-v1", "operation_id": row["id"],
                "state": state, "reset_id": row["reset_id"], "claimable": state == "ready"}

    def operation(self, operation_id, token, pending):
        self.expire()
        with self.store.tx() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                reject(404, "operation_not_found")
            if row["owner_hash"] != token_hash(pending):
                session = self._session(db, token)
                if row["generation"] != session["lease_generation"]:
                    reject(403, "operation_forbidden")
            return self._operation(row)

    def reset_status(self, reset_id, token, pending):
        self.expire()
        with self.store.tx() as db:
            row = db.execute("SELECT * FROM resets WHERE id=?", (reset_id,)).fetchone()
            if row is None:
                reject(404, "reset_not_found")
            owned = db.execute("SELECT 1 FROM operations WHERE reset_id=? AND owner_hash=?",
                               (reset_id, token_hash(pending))).fetchone()
            if not owned:
                session = self._session(db, token)
                if row["generation"] != session["lease_generation"]:
                    reject(403, "reset_forbidden")
            return {k: row[k] for k in ("state", "phase", "error_code")}

    def claim(self, operation_id, attempt_operation_id, token, pending):
        self.expire()
        with self.store.tx() as db:
            fingerprint = self._fingerprint("claim", [operation_id, attempt_operation_id])
            claim = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if claim:
                if claim["kind"] != "claim" or claim["request_hash"] != fingerprint:
                    reject(409, "operation_conflict")
                if claim["session_hash"] == token_hash(token):
                    return self._session(db, token), None
                reject(409, "lease_cookie_lost")
            op = db.execute("SELECT * FROM operations WHERE id=?", (attempt_operation_id,)).fetchone()
            if op is None:
                reject(404, "operation_not_found")
            if op["state"] == "claimed" and op["session_hash"] == token_hash(token):
                return self._session(db, token), None
            if op["owner_hash"] != token_hash(pending):
                reject(401, "attempt_cookie_required")
            if op["state"] == "claimed":
                reject(409, "lease_cookie_lost")
            slot = db.execute("SELECT * FROM slot").fetchone()
            if slot["state"] == "degraded":
                reject(503, "reset_failed")
            if op["kind"] not in ("login", "takeover") or op["state"] != "ready" or slot["generation"] != op["generation"]:
                reject(409, "attempt_not_ready")
            raw = secrets.token_urlsafe(32)
            expires = self.clock() + self.config.ttl_minutes * 60
            db.execute("INSERT INTO sessions VALUES (?,?,?,NULL,NULL)", (token_hash(raw), op["generation"], expires))
            db.execute("UPDATE operations SET state='claimed',session_hash=? WHERE id=? AND state='ready'",
                       (token_hash(raw), attempt_operation_id))
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?)", (operation_id, "claim",
                       fingerprint, token_hash(pending), op["generation"], op["reset_id"], "claimed",
                       expires, token_hash(raw)))
            db.execute("UPDATE slot SET state='active',session_hash=?,expires=? WHERE id=1",
                       (token_hash(raw), expires))
            return self._session(db, raw), raw

    def logout(self, operation_id, token):
        self.expire()
        with self.store.tx() as db:
            op = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if op:
                if op["kind"] != "logout" or op["owner_hash"] != token_hash(token):
                    reject(409, "operation_conflict")
                return self._operation(op)
            self._session(db, token)
            slot = db.execute("SELECT * FROM slot").fetchone()
            reset_id, generation = str(uuid4()), slot["generation"] + 1
            db.execute("UPDATE sessions SET revoked='logged_out',owner_until=NULL WHERE hash=?", (token_hash(token),))
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,NULL)", (
                operation_id, "logout", self._fingerprint("logout", operation_id), token_hash(token),
                generation, reset_id, "pending", self.clock() + 300))
            self._new_reset(db, reset_id, generation)
        self._launch_reset(reset_id, generation)
        return {"state": "resetting", "reset_id": reset_id}

    def _new_reset(self, db, reset_id, generation):
        db.execute("INSERT INTO resets VALUES (?,?,'running','retiring',NULL)", (reset_id, generation))
        db.execute("UPDATE slot SET state='resetting',generation=?,session_hash=NULL,expires=NULL,reset_id=?",
                   (generation, reset_id))

    def _begin_cleanup(self):
        with self.store.tx() as db:
            slot = db.execute("SELECT * FROM slot").fetchone()
            reset_id, generation = str(uuid4()), slot["generation"] + 1
            self._new_reset(db, reset_id, generation)
        self._launch_reset(reset_id, generation)

    def _launch_reset(self, reset_id, generation):
        self.reset_task = asyncio.create_task(self._reset(reset_id, generation))

    async def _reset(self, reset_id, generation):
        try:
            handle = await self.manager.reset(generation)
            with self.store.tx() as db:
                slot = db.execute("SELECT * FROM slot").fetchone()
                if slot["generation"] != generation or slot["reset_id"] != reset_id:
                    raise RuntimeError("Reset publication CAS failed")
                db.execute("UPDATE resets SET state='completed',phase='ready' WHERE id=?", (reset_id,))
                db.execute("UPDATE slot SET seed_version=? WHERE id=1", (handle.seed_version,))
                db.execute("UPDATE operations SET state='ready' WHERE reset_id=? AND state='pending' AND deadline>? "
                           "AND kind IN ('login','takeover')", (reset_id, self.clock()))
                reservation = db.execute("SELECT 1 FROM operations WHERE reset_id=? AND state='ready'", (reset_id,)).fetchone()
                if not reservation:
                    db.execute("UPDATE operations SET state=CASE WHEN kind='logout' THEN 'completed' ELSE 'expired' END "
                               "WHERE reset_id=? AND state='pending'", (reset_id,))
                    db.execute("UPDATE slot SET state='available'")
        except Exception:
            with self.store.tx() as db:
                db.execute("UPDATE slot SET state='degraded',session_hash=NULL,expires=NULL WHERE generation=?", (generation,))
                db.execute("UPDATE resets SET state='failed',phase='failed',error_code='reset_failed' WHERE id=?", (reset_id,))
                db.execute("UPDATE operations SET state='failed' WHERE reset_id=?", (reset_id,))

    def expire(self):
        cleanup = False
        with self.store.tx() as db:
            slot = db.execute("SELECT * FROM slot").fetchone()
            if slot["state"] == "active" and slot["expires"] <= self.clock():
                db.execute("UPDATE sessions SET revoked='expired',owner_until=NULL WHERE hash=?", (slot["session_hash"],))
                # Reserve reset under the same transaction; competing requests cannot allocate a lease.
                reset_id, generation = str(uuid4()), slot["generation"] + 1
                self._new_reset(db, reset_id, generation)
                cleanup = True
            elif slot["state"] == "resetting":
                expired = db.execute("SELECT 1 FROM operations WHERE reset_id=? AND state='ready' AND deadline<=?",
                                     (slot["reset_id"], self.clock())).fetchone()
                if expired:
                    db.execute("UPDATE operations SET state='expired' WHERE reset_id=? AND state='ready'", (slot["reset_id"],))
                    db.execute("UPDATE slot SET state='available'")
        if cleanup:
            self._launch_reset(reset_id, generation)

    async def _sweep_loop(self):
        while True:
            await asyncio.sleep(1)
            self.expire()
