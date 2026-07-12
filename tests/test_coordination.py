import json
import subprocess
import sys
import time

import pytest

from code_scientist.coordination import CoordinationError, SQLiteTaskCoordinator
from code_scientist.models import Evidence, Hypothesis, ResearchGoal, RunState, Task, TestPlan
from code_scientist.supervisor import _reconcile_coordinator_results
from code_scientist.task_execution import (
    ProviderRuntime,
    execute_task_packet,
    review_packet_digest,
)
from code_scientist.worker import WorkerTaskError, run_packet_worker


def _packet_task(
    task_id: str,
    *,
    priority: float = 1.0,
    depends_on: list[str] | None = None,
    resource_class: str = "review",
) -> Task:
    return Task(
        id=task_id,
        kind="packet",
        priority=priority,
        payload={
            "packet_type": "write_artifact",
            "output_path": f"worker-results/{task_id}.json",
            "content": {"task": task_id},
        },
        depends_on=depends_on or [],
        resource_class=resource_class,
    )


def test_sqlite_coordinator_honors_dependencies_leases_and_resource_limits(tmp_path):
    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    parent = _packet_task("task-parent", priority=1)
    child = _packet_task("task-child", priority=5, depends_on=[parent.id])
    independent = _packet_task("task-independent", priority=4)
    coordinator.sync_tasks([parent, child, independent])
    coordinator.set_resource_limits({"review": 1})

    first = coordinator.claim("worker-a", lease_seconds=30)
    assert first is not None
    assert first.id == independent.id
    assert coordinator.claim("worker-b", lease_seconds=30) is None

    coordinator.complete(first.id, "worker-a", ["result-independent"])
    second = coordinator.claim("worker-b", lease_seconds=30)
    assert second is not None
    assert second.id == parent.id
    coordinator.complete(second.id, "worker-b", ["result-parent"])
    third = coordinator.claim("worker-c", lease_seconds=30)
    assert third is not None
    assert third.id == child.id

    with pytest.raises(CoordinationError):
        coordinator.complete(third.id, "worker-not-owner", [])
    coordinator.complete(third.id, "worker-c", ["result-child"])
    assert [task.status for task in coordinator.list_tasks()] == [
        "completed",
        "completed",
        "completed",
    ]


def test_sqlite_coordinator_recovers_expired_worker_lease(tmp_path):
    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    coordinator.sync_tasks([_packet_task("task-expiring")])

    claimed = coordinator.claim("crashed-worker", lease_seconds=1)
    assert claimed is not None
    time.sleep(1.05)
    recovered = coordinator.claim("replacement-worker", lease_seconds=10)

    assert recovered is not None
    assert recovered.id == claimed.id
    assert recovered.attempts == 2
    assert any(event["event_type"] == "task_lease_expired" for event in coordinator.events())


def test_sqlite_coordinator_budget_is_atomic_and_fail_closed(tmp_path):
    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    coordinator.configure_budget("agent_tools", 2)

    assert coordinator.consume_budget("agent_tools") == (2, 1)
    assert coordinator.consume_budget("agent_tools") == (1, 0)
    with pytest.raises(CoordinationError, match="Budget exhausted"):
        coordinator.consume_budget("agent_tools")
    assert coordinator.budget_state("agent_tools") == (2, 2)


def test_sync_tasks_never_regresses_terminal_coordinator_state(tmp_path):
    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    task = _packet_task("task-terminal")
    coordinator.sync_tasks([task])
    claimed = coordinator.claim("worker-a")
    assert claimed is not None
    coordinator.complete(claimed.id, "worker-a", ["result-ref"])

    coordinator.sync_tasks([task])

    restored = coordinator.get_task(task.id)
    assert restored is not None
    assert restored.status == "completed"
    assert restored.result_refs == ["result-ref"]


def test_cli_workers_claim_each_packet_once_across_processes(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    coordinator = SQLiteTaskCoordinator(run_dir / "coordination.sqlite3")
    tasks = [_packet_task(f"task-{index}", resource_class="review") for index in range(6)]
    coordinator.sync_tasks(tasks)
    coordinator.set_resource_limits({"review": 3})

    # Workers need --max-tasks (not --once): a --once worker that polls while
    # all resource slots are momentarily busy exits with zero tasks and its
    # packet would never be claimed, because every other worker stops after
    # one task. With a full allowance, surviving workers drain the queue.
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "code_scientist.cli",
                "worker",
                str(run_dir),
                "--worker-id",
                f"process-{index}",
                "--max-tasks",
                str(len(tasks)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(len(tasks))
    ]
    outputs = [process.communicate(timeout=60) for process in processes]

    assert all(process.returncode == 0 for process in processes), outputs
    assert sum(json.loads(stdout)["completed_tasks"] for stdout, _stderr in outputs) == len(tasks)
    completed = coordinator.list_tasks()
    assert all(task.status == "completed" for task in completed)
    assert len({task.result_refs[0] for task in completed}) == len(tasks)
    assert len([event for event in coordinator.events() if event["event_type"] == "task_claimed"]) == len(tasks)
    for task in tasks:
        artifact = json.loads((run_dir / "worker-results" / f"{task.id}.json").read_text())
        assert artifact["content"]["task"] == task.id


def test_serialized_deterministic_review_packet_writes_portable_result(tmp_path):
    goal = ResearchGoal.from_objective("Improve coding-agent recovery")
    evidence = Evidence(
        id="ev-benchmark",
        kind="benchmark",
        source="fixture",
        content="Recovery protocol improved pass rate while reducing regressions.",
    )
    hypothesis = Hypothesis(
        id="hyp-recovery",
        title="Recovery protocol",
        claim="A recovery protocol improves coding-agent reliability.",
        rationale="Benchmark failures expose recoverable states.",
        assumptions=["Failure states are detectable."],
        evidence_refs=[evidence.id],
        test_plan=TestPlan(
            experiment="Compare protocol against baseline.",
            metrics=["pass_rate", "regression_count"],
            success_condition="Pass rate increases without more regressions.",
        ),
        risks=["Added latency"],
        origin="test",
    )
    review_payload = {
        "cycle": 1,
        "packet_type": "deterministic_review",
        "required_provider": "deterministic",
        "requested_max_tokens": 1024,
        "use_grounded": True,
        "hypothesis_id": hypothesis.id,
        "goal": goal.to_dict(),
        "hypothesis": hypothesis.to_dict(),
        "evidence": [evidence.to_dict()],
        "review_types": ["initial_review"],
    }
    review_payload["packet_digest"] = review_packet_digest(review_payload)
    task = Task(
        id="task-review-packet",
        kind="review",
        priority=1,
        payload=review_payload,
        resource_class="review",
    )

    refs = execute_task_packet(task, tmp_path)

    output = tmp_path / "worker-results" / f"{task.id}.json"
    data = json.loads(output.read_text())
    assert refs == [data["review"]["id"], str(output)]
    assert data["review"]["hypothesis_id"] == hypothesis.id
    assert data["review"]["review_type"] == "initial_review"

    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    coordinator.sync_tasks([task])
    claimed = coordinator.claim("review-process")
    assert claimed is not None
    coordinator.complete(claimed.id, "review-process", refs)

    reconciled = _reconcile_coordinator_results(
        tmp_path,
        RunState(goal=goal, task_queue=[task]),
    )

    assert reconciled.task_queue[0].status == "completed"
    assert [review.id for review in reconciled.reviews] == [data["review"]["id"]]
    assert reconciled.agent_traces[0].task_id == task.id


def test_provider_review_packet_reconstructs_approved_client_without_serializing_secret(tmp_path):
    goal = ResearchGoal.from_objective("Improve coding-agent reliability")
    hypothesis = Hypothesis(
        id="hyp-provider-review",
        title="Evidence gate",
        claim="An evidence gate improves coding-agent reliability.",
        rationale="It rejects unsupported edits.",
        assumptions=["Evidence can be retrieved."],
        evidence_refs=[],
        test_plan=TestPlan(
            experiment="Compare evidence-gated and baseline agents.",
            metrics=["pass_rate"],
            success_condition="Pass rate improves.",
        ),
        risks=["Latency"],
        origin="test",
    )
    provider_payload = {
        "cycle": 1,
        "packet_type": "provider_review",
        "required_provider": "anthropic",
        "required_model": "test-model",
        "requested_max_tokens": 321,
        "use_grounded": False,
        "hypothesis_id": hypothesis.id,
        "goal": goal.to_dict(),
        "hypothesis": hypothesis.to_dict(),
        "evidence": [],
        "review_types": ["initial_review"],
        "reflection_feedback": ["Require benchmark evidence."],
    }
    provider_payload["packet_digest"] = review_packet_digest(provider_payload)
    task = Task(
        id="task-provider-review",
        kind="review",
        priority=1,
        payload=provider_payload,
        resource_class="review",
    )
    factory_calls: list[tuple[str, str, str]] = []

    class FakeProviderClient:
        def complete(self, prompt, max_tokens):
            assert "Require benchmark evidence." in prompt
            assert max_tokens == 321
            return json.dumps(
                {
                    "decision": "revise",
                    "scores": {
                        "alignment": 5,
                        "plausibility": 3,
                        "novelty": 3,
                        "testability": 5,
                        "safety": 5,
                    },
                    "strengths": ["Measurable."],
                    "weaknesses": ["Needs benchmark evidence."],
                    "safety_notes": ["Human review required."],
                    "findings": ["Provider review completed."],
                    "confidence": 0.8,
                    "requires_revision": True,
                    "evidence_refs": [],
                }
            )

    def factory(provider: str, model: str, env_file: str):
        factory_calls.append((provider, model, env_file))
        return FakeProviderClient()

    refs = execute_task_packet(
        task,
        tmp_path,
        provider_client_factory=factory,
        provider_runtime=ProviderRuntime(
            provider="anthropic",
            model="test-model",
            env_file=str(tmp_path / ".env"),
            max_tokens=321,
        ),
    )

    assert factory_calls == [("anthropic", "test-model", str(tmp_path / ".env"))]
    assert "api_key" not in json.dumps(task.to_dict()).lower()
    result = json.loads((tmp_path / "worker-results" / f"{task.id}.json").read_text())
    assert result["provider"] == "anthropic"
    assert result["model"] == "test-model"
    assert result["reviews"][0]["decision"] == "revise"
    assert result["agent_trace"]["llm_interactions"]
    assert refs[0] == result["reviews"][0]["id"]


def test_provider_deep_review_consumes_process_safe_budget_per_request(tmp_path):
    goal = ResearchGoal.from_objective("Improve coding-agent reliability")
    hypothesis = Hypothesis(
        id="hyp-deep-provider",
        title="Assumption gate",
        claim="An assumption gate improves coding-agent reliability.",
        rationale="It tests premises before edits.",
        assumptions=["Premises can be tested."],
        evidence_refs=[],
        test_plan=TestPlan("Compare workflows.", ["pass_rate"], "Pass rate improves."),
        risks=["Latency"],
        origin="test",
    )
    payload = {
        "cycle": 1,
        "packet_type": "provider_review",
        "required_provider": "anthropic",
        "required_model": "test-model",
        "requested_max_tokens": 300,
        "use_grounded": False,
        "hypothesis_id": hypothesis.id,
        "goal": goal.to_dict(),
        "hypothesis": hypothesis.to_dict(),
        "evidence": [],
        "review_types": ["deep_verification"],
    }
    payload["packet_digest"] = review_packet_digest(payload)
    task = Task("task-deep-provider", "review", 1, payload=payload, resource_class="review")

    class FakeDeepClient:
        def complete(self, prompt, max_tokens):
            if "claim mechanism" in prompt.lower():
                return "Mechanism analysis."
            if "assumption risk audit" in prompt.lower():
                return json.dumps({"assumption_checks": []})
            return json.dumps(
                {
                    "decision": "revise",
                    "scores": {"alignment": 4, "plausibility": 3, "novelty": 3, "testability": 4, "safety": 5},
                    "strengths": ["Testable."],
                    "weaknesses": ["Needs evidence."],
                    "safety_notes": [],
                    "findings": ["Deep review complete."],
                    "confidence": 0.7,
                    "requires_revision": True,
                    "evidence_refs": [],
                    "assumption_checks": [],
                }
            )

    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    coordinator.configure_budget("provider_calls", 3)
    execute_task_packet(
        task,
        tmp_path,
        provider_client_factory=lambda *_args: FakeDeepClient(),
        provider_runtime=ProviderRuntime(
            provider="anthropic",
            model="test-model",
            max_tokens=300,
            coordinator=coordinator,
        ),
    )

    assert coordinator.budget_state("provider_calls") == (3, 3)


def test_provider_packets_fail_closed_on_runtime_policy_and_expired_lease(tmp_path):
    payload = {
        "cycle": 1,
        "packet_type": "provider_review",
        "required_provider": "anthropic",
        "required_model": "approved-model",
        "requested_max_tokens": 500,
        "use_grounded": False,
        "hypothesis_id": "hyp-1",
        "goal": ResearchGoal.from_objective("Improve agents").to_dict(),
        "hypothesis": Hypothesis(
            id="hyp-1",
            title="Test",
            claim="Test agents.",
            rationale="Test.",
            assumptions=["Testable."],
            evidence_refs=[],
            test_plan=TestPlan("Test.", ["pass_rate"], "Improve."),
            risks=[],
            origin="test",
        ).to_dict(),
        "evidence": [],
        "review_types": ["initial_review"],
    }
    payload["packet_digest"] = review_packet_digest(payload)
    task = Task("task-provider-policy", "review", 1, payload=payload, resource_class="review")

    with pytest.raises(ValueError, match="not authorized"):
        execute_task_packet(task, tmp_path)
    with pytest.raises(ValueError, match="token cap"):
        execute_task_packet(
            task,
            tmp_path,
            provider_runtime=ProviderRuntime(
                provider="anthropic",
                model="approved-model",
                max_tokens=100,
            ),
            provider_client_factory=lambda *_args: object(),
        )

    coordinator = SQLiteTaskCoordinator(tmp_path / "lease.sqlite3")
    coordinator.sync_tasks([task])
    assert coordinator.claim("provider-worker", lease_seconds=1) is not None
    time.sleep(1.05)
    coordinator.expire_leases()
    expired = coordinator.get_task(task.id)
    assert expired is not None
    assert expired.status == "failed"
    assert "manual review required" in expired.error


def test_packet_worker_exits_as_failure_when_task_retries_are_exhausted(tmp_path):
    run_dir = tmp_path / "failed-run"
    run_dir.mkdir()
    task = Task(
        id="task-invalid-artifact",
        kind="packet",
        priority=1,
        payload={"packet_type": "write_artifact", "content": ["not", "an", "object"]},
    )
    coordinator = SQLiteTaskCoordinator(run_dir / "coordination.sqlite3")
    coordinator.sync_tasks([task])

    with pytest.raises(WorkerTaskError, match=task.id):
        run_packet_worker(
            run_dir,
            "failing-worker",
            max_tasks=1,
            stop_when_idle=True,
            eligible_task_ids={task.id},
        )

    failed = coordinator.get_task(task.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 3


def test_provider_worker_does_not_claim_deterministic_review_packets(tmp_path):
    run_dir = tmp_path / "provider-scope"
    run_dir.mkdir()
    goal = ResearchGoal.from_objective("Improve coding-agent reliability")
    hypothesis = Hypothesis(
        id="hyp-deterministic-only",
        title="Deterministic packet",
        claim="A deterministic review packet remains deterministic.",
        rationale="Provider authority must not broaden task eligibility.",
        assumptions=["Packet types are enforced."],
        evidence_refs=[],
        test_plan=TestPlan("Review the packet.", ["decision"], "A decision is recorded."),
        risks=[],
        origin="test",
    )
    payload = {
        "cycle": 1,
        "packet_type": "deterministic_review",
        "required_provider": "deterministic",
        "requested_max_tokens": 128,
        "use_grounded": False,
        "hypothesis_id": hypothesis.id,
        "goal": goal.to_dict(),
        "hypothesis": hypothesis.to_dict(),
        "evidence": [],
        "review_types": ["initial_review"],
    }
    payload["packet_digest"] = review_packet_digest(payload)
    task = Task("task-deterministic-only", "review", 1, payload=payload)
    coordinator = SQLiteTaskCoordinator(run_dir / "coordination.sqlite3")
    coordinator.sync_tasks([task])

    completed = run_packet_worker(
        run_dir,
        "anthropic-worker",
        max_tasks=1,
        stop_when_idle=True,
        provider="anthropic",
        model="approved-model",
        provider_call_budget=1,
        provider_client_factory=lambda *_args: pytest.fail("provider client should not be created"),
    )

    assert completed == 0
    untouched = coordinator.get_task(task.id)
    assert untouched is not None
    assert untouched.status == "queued"
    assert untouched.attempts == 0


def test_provider_review_packet_executes_with_claude_cli_runtime(tmp_path):
    goal = ResearchGoal.from_objective("Improve coding-agent reliability")
    hypothesis = Hypothesis(
        id="hyp-claude-cli-review",
        title="Assumption gate",
        claim="An assumption gate improves coding-agent reliability.",
        rationale="It tests premises before edits.",
        assumptions=["Premises can be tested."],
        evidence_refs=[],
        test_plan=TestPlan("Compare workflows.", ["pass_rate"], "Pass rate improves."),
        risks=["Latency"],
        origin="test",
    )
    payload = {
        "cycle": 1,
        "packet_type": "provider_review",
        "required_provider": "claude-cli",
        "required_model": "claude-haiku-4-5",
        "requested_max_tokens": 321,
        "use_grounded": False,
        "hypothesis_id": hypothesis.id,
        "goal": goal.to_dict(),
        "hypothesis": hypothesis.to_dict(),
        "evidence": [],
        "review_types": ["initial_review"],
    }
    payload["packet_digest"] = review_packet_digest(payload)
    task = Task(
        id="task-claude-cli-review",
        kind="review",
        priority=1,
        payload=payload,
        resource_class="review",
    )
    factory_calls: list[tuple[str, str, str]] = []

    class FakeProviderClient:
        def complete(self, prompt, max_tokens):
            return json.dumps(
                {
                    "decision": "revise",
                    "scores": {
                        "alignment": 5,
                        "plausibility": 3,
                        "novelty": 3,
                        "testability": 5,
                        "safety": 5,
                    },
                    "strengths": ["Measurable."],
                    "weaknesses": ["Needs benchmark evidence."],
                    "safety_notes": ["Human review required."],
                    "findings": ["Provider review completed."],
                    "confidence": 0.8,
                    "requires_revision": True,
                    "evidence_refs": [],
                }
            )

    def factory(provider: str, model: str, env_file: str):
        factory_calls.append((provider, model, env_file))
        return FakeProviderClient()

    refs = execute_task_packet(
        task,
        tmp_path,
        provider_client_factory=factory,
        provider_runtime=ProviderRuntime(
            provider="claude-cli",
            model="claude-haiku-4-5",
            env_file=str(tmp_path / ".env"),
            max_tokens=321,
        ),
    )

    assert factory_calls == [("claude-cli", "claude-haiku-4-5", str(tmp_path / ".env"))]
    result = json.loads((tmp_path / "worker-results" / f"{task.id}.json").read_text())
    assert result["provider"] == "claude-cli"
    assert result["reviews"][0]["decision"] == "revise"
    assert refs[0] == result["reviews"][0]["id"]


def test_run_packet_worker_validates_host_cli_providers(tmp_path):
    with pytest.raises(ValueError, match="positive provider call budget"):
        run_packet_worker(tmp_path, "worker-1", provider="claude-cli", provider_call_budget=0)

    with pytest.raises(ValueError, match="Unsupported worker provider"):
        run_packet_worker(tmp_path, "worker-1", provider="openai")

    with pytest.raises(ValueError, match="Unsupported worker provider"):
        run_packet_worker(tmp_path, "worker-1", provider="host-agent", provider_call_budget=5)
