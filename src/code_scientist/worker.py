from __future__ import annotations

import time
import threading
from collections.abc import Callable
from pathlib import Path

from code_scientist.coordination import SQLiteTaskCoordinator
from code_scientist.llm import WORKER_PROVIDER_CHOICES, is_llm_provider, resolve_provider_model
from code_scientist.models import Task
from code_scientist.task_execution import (
    ProviderClientFactory,
    ProviderRuntime,
    execute_task_packet,
)


class WorkerTaskError(RuntimeError):
    pass


def run_coordinated_worker(
    coordinator: SQLiteTaskCoordinator,
    worker_id: str,
    execute: Callable[[Task], list[str] | None],
    *,
    lease_seconds: float = 60,
    max_attempts: int = 3,
    max_tasks: int | None = None,
    poll_seconds: float = 1,
    stop_when_idle: bool = False,
    eligible_task_ids: set[str] | None = None,
    eligible_packet_types: set[str] | None = None,
    raise_on_failed: bool = False,
) -> int:
    completed = 0
    while max_tasks is None or completed < max_tasks:
        task = coordinator.claim(
            worker_id,
            lease_seconds=lease_seconds,
            eligible_task_ids=eligible_task_ids,
            eligible_packet_types=eligible_packet_types,
        )
        if task is None:
            if stop_when_idle:
                break
            time.sleep(max(float(poll_seconds), 0.01))
            continue
        heartbeat_stop = threading.Event()
        heartbeat_errors: list[Exception] = []

        def heartbeat_loop() -> None:
            interval = max(float(lease_seconds) / 3.0, 0.25)
            while not heartbeat_stop.wait(interval):
                try:
                    coordinator.heartbeat(
                        task.id,
                        worker_id,
                        lease_seconds=lease_seconds,
                    )
                except Exception as exc:
                    heartbeat_errors.append(exc)
                    return

        heartbeat = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat.start()
        try:
            result_refs = execute(task) or []
        except Exception as exc:
            heartbeat_stop.set()
            heartbeat.join(timeout=1)
            failed = coordinator.fail(task.id, worker_id, str(exc), max_attempts=max_attempts)
            if raise_on_failed and failed.status == "failed":
                raise WorkerTaskError(f"Task {task.id} failed: {failed.error}") from exc
        else:
            heartbeat_stop.set()
            heartbeat.join(timeout=1)
            if heartbeat_errors:
                raise heartbeat_errors[0]
            coordinator.complete(task.id, worker_id, list(result_refs))
            completed += 1
    return completed


def run_packet_worker(
    run_dir: str | Path,
    worker_id: str,
    *,
    lease_seconds: float = 60,
    max_attempts: int = 3,
    max_tasks: int | None = None,
    poll_seconds: float = 1,
    stop_when_idle: bool = False,
    eligible_task_ids: set[str] | None = None,
    provider: str = "deterministic",
    model: str = "",
    env_file: str = ".env",
    max_tokens: int = 4096,
    provider_call_budget: int = 0,
    provider_client_factory: ProviderClientFactory | None = None,
) -> int:
    root = Path(run_dir)
    coordinator = SQLiteTaskCoordinator(root / "coordination.sqlite3")
    normalized_provider = provider.strip().lower()
    if normalized_provider not in WORKER_PROVIDER_CHOICES:
        raise ValueError(f"Unsupported worker provider: {provider}")
    if is_llm_provider(normalized_provider):
        if provider_call_budget <= 0:
            raise ValueError("Provider workers require a positive provider call budget")
        coordinator.configure_budget("provider_calls", provider_call_budget)
    runtime = ProviderRuntime(
        provider=normalized_provider,
        model=resolve_provider_model(normalized_provider, model),
        env_file=env_file,
        max_tokens=max_tokens,
        coordinator=coordinator if is_llm_provider(normalized_provider) else None,
    )
    packet_types = {"write_artifact"}
    packet_types.add(
        "provider_review" if is_llm_provider(normalized_provider) else "deterministic_review"
    )
    return run_coordinated_worker(
        coordinator,
        worker_id,
        lambda task: execute_task_packet(
            task,
            root,
            provider_client_factory=provider_client_factory,
            provider_runtime=runtime,
        ),
        lease_seconds=lease_seconds,
        max_attempts=1 if is_llm_provider(normalized_provider) else max_attempts,
        max_tasks=max_tasks,
        poll_seconds=poll_seconds,
        stop_when_idle=stop_when_idle,
        eligible_task_ids=eligible_task_ids,
        eligible_packet_types=packet_types,
        raise_on_failed=True,
    )
