from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from code_scientist.models import Task


class CoordinationError(RuntimeError):
    pass


@contextmanager
def state_file_lock(
    path: str | Path,
    *,
    timeout_seconds: float = 30.0,
    stale_after_seconds: float = 300.0,
):
    """Serialize state mutations across Python and Node processes.

    The lock-file protocol intentionally uses only O_EXCL creation, mtime-based
    stale recovery, and owner tokens so the web workbench can implement the
    same contract without a platform-specific advisory-lock dependency.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.with_name(f".{destination.name}.lock")
    owner = f"{os.getpid()}-{uuid4().hex}"
    deadline = time.monotonic() + max(float(timeout_seconds), 0.1)
    stale_after = max(float(stale_after_seconds), 1.0)
    acquired = False
    while not acquired:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                stat = lock_path.stat()
                observed_mtime = stat.st_mtime_ns
            except FileNotFoundError:
                continue
            if time.time() - stat.st_mtime > stale_after:
                try:
                    if lock_path.stat().st_mtime_ns == observed_mtime:
                        lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise CoordinationError(f"Timed out waiting for state lock: {lock_path}")
            time.sleep(0.025)
            continue
        try:
            os.write(
                descriptor,
                json.dumps({"owner": owner, "created_at": time.time()}).encode("utf-8"),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        acquired = True
    try:
        yield
    finally:
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        if payload.get("owner") == owner:
            lock_path.unlink(missing_ok=True)


class SQLiteTaskCoordinator:
    """Durable multi-process task, lease, resource, and budget coordinator."""

    def __init__(self, path: str | Path, *, default_resource_limit: int = 1) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.default_resource_limit = max(int(default_resource_limit), 1)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    priority REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    result_refs_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    worker_state_json TEXT NOT NULL DEFAULT '{}',
                    resource_class TEXT NOT NULL DEFAULT 'default',
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_expires_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    dependency_id TEXT NOT NULL,
                    PRIMARY KEY (task_id, dependency_id)
                );
                CREATE TABLE IF NOT EXISTS resource_limits (
                    resource_class TEXT PRIMARY KEY,
                    max_active INTEGER NOT NULL CHECK (max_active >= 1)
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    name TEXT PRIMARY KEY,
                    budget_limit INTEGER NOT NULL CHECK (budget_limit >= 0),
                    used INTEGER NOT NULL DEFAULT 0 CHECK (used >= 0),
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS named_leases (
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    task_id TEXT NOT NULL DEFAULT '',
                    worker_id TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS human_commands (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_claim
                    ON tasks(status, priority DESC, id);
                CREATE INDEX IF NOT EXISTS idx_tasks_lease
                    ON tasks(status, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_events_task
                    ON events(task_id, sequence);
                """
            )

    def sync_tasks(self, tasks: Iterable[Task]) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for task in tasks:
                    connection.execute(
                        """
                        INSERT INTO tasks (
                            id, kind, priority, payload_json, status, attempts,
                            result_refs_json, error, worker_state_json, resource_class,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            kind=excluded.kind,
                            priority=excluded.priority,
                            payload_json=excluded.payload_json,
                            status=CASE
                                WHEN tasks.status IN ('completed', 'failed', 'superseded')
                                THEN tasks.status
                                WHEN tasks.status='running'
                                  AND tasks.lease_expires_at > excluded.updated_at
                                THEN tasks.status ELSE excluded.status END,
                            attempts=MAX(tasks.attempts, excluded.attempts),
                            result_refs_json=CASE
                                WHEN tasks.status IN ('completed', 'failed', 'superseded')
                                THEN tasks.result_refs_json
                                WHEN tasks.status='running'
                                  AND tasks.lease_expires_at > excluded.updated_at
                                THEN tasks.result_refs_json ELSE excluded.result_refs_json END,
                            error=CASE
                                WHEN tasks.status IN ('completed', 'failed', 'superseded')
                                THEN tasks.error
                                WHEN tasks.status='running'
                                  AND tasks.lease_expires_at > excluded.updated_at
                                THEN tasks.error ELSE excluded.error END,
                            worker_state_json=CASE
                                WHEN tasks.status IN ('completed', 'failed', 'superseded')
                                THEN tasks.worker_state_json
                                WHEN tasks.status='running'
                                  AND tasks.lease_expires_at > excluded.updated_at
                                THEN tasks.worker_state_json ELSE excluded.worker_state_json END,
                            resource_class=excluded.resource_class,
                            updated_at=excluded.updated_at
                        """,
                        (
                            task.id,
                            task.kind,
                            float(task.priority),
                            _json(task.payload),
                            task.status,
                            int(task.attempts),
                            _json(task.result_refs),
                            task.error,
                            _json(task.worker_state),
                            task.resource_class or "default",
                            now,
                            now,
                        ),
                    )
                    connection.execute("DELETE FROM task_dependencies WHERE task_id=?", (task.id,))
                    connection.executemany(
                        "INSERT OR IGNORE INTO task_dependencies(task_id, dependency_id) VALUES (?, ?)",
                        [(task.id, dependency_id) for dependency_id in task.depends_on],
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def set_resource_limits(self, limits: dict[str, int]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.executemany(
                    """
                    INSERT INTO resource_limits(resource_class, max_active) VALUES (?, ?)
                    ON CONFLICT(resource_class) DO UPDATE SET max_active=excluded.max_active
                    """,
                    [(name, max(int(limit), 1)) for name, limit in limits.items()],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def claim(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 60,
        eligible_kinds: set[str] | None = None,
        eligible_task_ids: set[str] | None = None,
        eligible_packet_types: set[str] | None = None,
    ) -> Task | None:
        owner = worker_id.strip()
        if not owner:
            raise ValueError("worker_id is required")
        now = time.time()
        expires_at = now + max(float(lease_seconds), 1.0)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._expire_leases(connection, now)
                rows = connection.execute(
                    "SELECT * FROM tasks WHERE status='queued' ORDER BY priority DESC, id"
                ).fetchall()
                for row in rows:
                    if eligible_kinds is not None and row["kind"] not in eligible_kinds:
                        continue
                    if eligible_task_ids is not None and row["id"] not in eligible_task_ids:
                        continue
                    if (
                        eligible_packet_types is not None
                        and str(_object(row["payload_json"]).get("packet_type", ""))
                        not in eligible_packet_types
                    ):
                        continue
                    if not self._dependencies_satisfied(connection, row["id"]):
                        continue
                    resource_class = row["resource_class"] or "default"
                    limit_row = connection.execute(
                        "SELECT max_active FROM resource_limits WHERE resource_class=?",
                        (resource_class,),
                    ).fetchone()
                    limit = int(limit_row[0]) if limit_row else self.default_resource_limit
                    active = int(
                        connection.execute(
                            """
                            SELECT COUNT(*) FROM tasks
                            WHERE status='running' AND resource_class=? AND lease_expires_at>?
                            """,
                            (resource_class, now),
                        ).fetchone()[0]
                    )
                    if active >= limit:
                        continue
                    attempt = int(row["attempts"]) + 1
                    worker_state = _object(row["worker_state_json"])
                    worker_state.update(
                        {
                            "phase": "running",
                            "last_event": "lease_claimed",
                            "attempt": attempt,
                            "lease_owner": owner,
                            "lease_expires_at": expires_at,
                        }
                    )
                    changed = connection.execute(
                        """
                        UPDATE tasks SET status='running', attempts=?, error='',
                            worker_state_json=?, lease_owner=?, lease_expires_at=?, updated_at=?
                        WHERE id=? AND status='queued'
                        """,
                        (attempt, _json(worker_state), owner, expires_at, now, row["id"]),
                    ).rowcount
                    if changed != 1:
                        continue
                    self._event(
                        connection,
                        "task_claimed",
                        row["id"],
                        owner,
                        {"lease_expires_at": expires_at, "attempt": attempt},
                        now,
                    )
                    connection.commit()
                    return self.get_task(row["id"])
                connection.commit()
                return None
            except Exception:
                connection.rollback()
                raise

    def heartbeat(self, task_id: str, worker_id: str, *, lease_seconds: float = 60) -> Task:
        now = time.time()
        expires_at = now + max(float(lease_seconds), 1.0)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                """
                UPDATE tasks SET lease_expires_at=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?
                """,
                (expires_at, now, task_id, worker_id, now),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise CoordinationError("Task lease is missing, expired, or owned by another worker.")
            self._event(connection, "task_heartbeat", task_id, worker_id, {"lease_expires_at": expires_at}, now)
            connection.commit()
        task = self.get_task(task_id)
        if task is None:
            raise CoordinationError(f"Task disappeared after heartbeat: {task_id}")
        return task

    def complete(self, task_id: str, worker_id: str, result_refs: list[str] | None = None) -> Task:
        return self._finish(task_id, worker_id, "completed", result_refs or [], "")

    def fail(
        self,
        task_id: str,
        worker_id: str,
        error: str,
        *,
        max_attempts: int = 3,
    ) -> Task:
        current = self.get_task(task_id)
        if current is None:
            raise CoordinationError(f"Unknown task: {task_id}")
        status = "failed" if current.attempts >= max(int(max_attempts), 1) else "queued"
        return self._finish(task_id, worker_id, status, [], error)

    def _finish(
        self,
        task_id: str,
        worker_id: str,
        status: str,
        result_refs: list[str],
        error: str,
    ) -> Task:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if (
                row is None
                or row["status"] != "running"
                or row["lease_owner"] != worker_id
                or float(row["lease_expires_at"] or 0) <= now
            ):
                connection.rollback()
                raise CoordinationError("Task lease is missing, expired, or owned by another worker.")
            worker_state = _object(row["worker_state_json"])
            worker_state.pop("lease_owner", None)
            worker_state.pop("lease_expires_at", None)
            worker_state.update(
                {
                    "phase": status,
                    "last_event": "completed" if status == "completed" else "failed",
                    "result_refs": result_refs,
                    "last_error": error,
                }
            )
            connection.execute(
                """
                UPDATE tasks SET status=?, result_refs_json=?, error=?, worker_state_json=?,
                    lease_owner='', lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (status, _json(result_refs), error, _json(worker_state), now, task_id),
            )
            self._event(
                connection,
                f"task_{status}",
                task_id,
                worker_id,
                {"result_refs": result_refs, "error": error},
                now,
            )
            connection.commit()
        task = self.get_task(task_id)
        if task is None:
            raise CoordinationError(f"Task disappeared after completion: {task_id}")
        return task

    def expire_leases(self) -> int:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = self._expire_leases(connection, now)
            connection.commit()
            return count

    def _expire_leases(self, connection: sqlite3.Connection, now: float) -> int:
        rows = connection.execute(
            "SELECT id, lease_owner, worker_state_json, payload_json FROM tasks "
            "WHERE status='running' AND lease_expires_at<=?",
            (now,),
        ).fetchall()
        for row in rows:
            state = _object(row["worker_state_json"])
            state.pop("lease_owner", None)
            state.pop("lease_expires_at", None)
            non_replayable = (
                str(_object(row["payload_json"]).get("packet_type", ""))
                == "provider_review"
            )
            recovered_status = "failed" if non_replayable else "queued"
            error = (
                "provider worker lease expired; manual review required before replay"
                if non_replayable
                else "worker lease expired"
            )
            state.update(
                {
                    "phase": recovered_status,
                    "last_event": (
                        "provider_lease_expired" if non_replayable else "lease_expired"
                    ),
                    "expired_lease_owner": row["lease_owner"],
                    "retryable": not non_replayable,
                }
            )
            connection.execute(
                """
                UPDATE tasks SET status=?, error=?,
                    worker_state_json=?, lease_owner='', lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (recovered_status, error, _json(state), now, row["id"]),
            )
            self._event(
                connection,
                "provider_task_lease_expired" if non_replayable else "task_lease_expired",
                row["id"],
                row["lease_owner"],
                {"retryable": not non_replayable},
                now,
            )
        return len(rows)

    def configure_budget(self, name: str, limit: int, *, used: int = 0) -> None:
        now = time.time()
        bounded_limit = max(int(limit), 0)
        bounded_used = min(max(int(used), 0), bounded_limit)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO budgets(name, budget_limit, used, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    budget_limit=excluded.budget_limit,
                    used=MAX(budgets.used, excluded.used),
                    updated_at=excluded.updated_at
                """,
                (name, bounded_limit, bounded_used, now),
            )

    def consume_budget(self, name: str, amount: int = 1) -> tuple[int, int]:
        requested = max(int(amount), 0)
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT budget_limit, used FROM budgets WHERE name=?", (name,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise CoordinationError(f"Budget is not configured: {name}")
            before = int(row["budget_limit"]) - int(row["used"])
            if requested > before:
                connection.rollback()
                raise CoordinationError(f"Budget exhausted: {name}")
            used = int(row["used"]) + requested
            connection.execute(
                "UPDATE budgets SET used=?, updated_at=? WHERE name=?",
                (used, now, name),
            )
            connection.commit()
            return before, int(row["budget_limit"]) - used

    def budget_state(self, name: str) -> tuple[int, int]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT budget_limit, used FROM budgets WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            raise CoordinationError(f"Budget is not configured: {name}")
        return int(row["budget_limit"]), int(row["used"])

    def acquire_named_lease(self, name: str, owner: str, *, lease_seconds: float = 60) -> bool:
        now = time.time()
        expires_at = now + max(float(lease_seconds), 1.0)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner, expires_at FROM named_leases WHERE name=?", (name,)
            ).fetchone()
            if row and row["owner"] != owner and float(row["expires_at"]) > now:
                connection.commit()
                return False
            connection.execute(
                """
                INSERT INTO named_leases(name, owner, expires_at, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,
                    expires_at=excluded.expires_at, updated_at=excluded.updated_at
                """,
                (name, owner, expires_at, now),
            )
            connection.commit()
            return True

    def enqueue_human_command(self, command_type: str, payload: dict[str, Any]) -> int:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO human_commands(command_type, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (command_type, _json(payload), now, now),
            )
            return int(cursor.lastrowid)

    def pending_human_commands(self, command_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM human_commands WHERE status='pending'"
        parameters: tuple[Any, ...] = ()
        if command_type:
            query += " AND command_type=?"
            parameters = (command_type,)
        query += " ORDER BY sequence"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "sequence": int(row["sequence"]),
                "command_type": row["command_type"],
                "payload": _object(row["payload_json"]),
            }
            for row in rows
        ]

    def complete_human_command(
        self,
        sequence: int,
        *,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        now = time.time()
        status = "failed" if error else "completed"
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE human_commands SET status=?, result_json=?, error=?, updated_at=?
                WHERE sequence=? AND status='pending'
                """,
                (status, _json(result or {}), error, now, int(sequence)),
            ).rowcount
        if changed != 1:
            raise CoordinationError(f"Pending human command not found: {sequence}")

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return None
            dependencies = [
                item[0]
                for item in connection.execute(
                    "SELECT dependency_id FROM task_dependencies WHERE task_id=? ORDER BY dependency_id",
                    (task_id,),
                ).fetchall()
            ]
            return _task_from_row(row, dependencies)

    def list_tasks(self) -> list[Task]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY priority DESC, id").fetchall()
            dependency_rows = connection.execute(
                "SELECT task_id, dependency_id FROM task_dependencies ORDER BY task_id, dependency_id"
            ).fetchall()
        dependencies: dict[str, list[str]] = {}
        for row in dependency_rows:
            dependencies.setdefault(row["task_id"], []).append(row["dependency_id"])
        return [_task_from_row(row, dependencies.get(row["id"], [])) for row in rows]

    def events(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        return [
            {
                "sequence": int(row["sequence"]),
                "occurred_at": float(row["occurred_at"]),
                "event_type": row["event_type"],
                "task_id": row["task_id"],
                "worker_id": row["worker_id"],
                "details": _object(row["details_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _dependencies_satisfied(connection: sqlite3.Connection, task_id: str) -> bool:
        unresolved = connection.execute(
            """
            SELECT COUNT(*) FROM task_dependencies d
            LEFT JOIN tasks dependency ON dependency.id=d.dependency_id
            WHERE d.task_id=? AND (dependency.id IS NULL OR dependency.status!='completed')
            """,
            (task_id,),
        ).fetchone()[0]
        return int(unresolved) == 0

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        event_type: str,
        task_id: str,
        worker_id: str,
        details: dict[str, Any],
        occurred_at: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events(occurred_at, event_type, task_id, worker_id, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (occurred_at, event_type, task_id, worker_id, _json(details)),
        )


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _task_from_row(row: sqlite3.Row, dependencies: list[str]) -> Task:
    worker_state = _object(row["worker_state_json"])
    if row["lease_owner"]:
        worker_state["lease_owner"] = row["lease_owner"]
    if row["lease_expires_at"] is not None:
        worker_state["lease_expires_at"] = float(row["lease_expires_at"])
    return Task(
        id=row["id"],
        kind=row["kind"],
        priority=float(row["priority"]),
        payload=_object(row["payload_json"]),
        status=row["status"],
        attempts=int(row["attempts"]),
        result_refs=list(_array(row["result_refs_json"])),
        error=row["error"],
        worker_state=worker_state,
        depends_on=dependencies,
        resource_class=row["resource_class"],
    )


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _object(value: str) -> dict[str, Any]:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _array(value: str) -> list[Any]:
    parsed = json.loads(value or "[]")
    return parsed if isinstance(parsed, list) else []
