import json
import subprocess
from pathlib import Path

import pytest

from code_scientist.cli import main
from code_scientist.experiments import (
    AgentInvocation,
    ClaudeCliAgentExecutor,
    DeterministicAgentExecutor,
    ExperimentAbort,
    ExperimentConfigError,
    HostAgentTrialExecutor,
    MEASURED_PROVENANCE,
    TrialSpec,
    _one_sided_binomial,
    benchmark_result_from_experiment,
    build_protocol,
    compute_experiment_stats,
    decide_verdict,
    grade_workspace,
    load_agent_tasks,
    pre_register_protocol,
    run_experiment,
)
from code_scientist.experiments import TrialArmResult
from code_scientist.models import BenchmarkResult, Hypothesis, TestPlan


BROKEN_MODULE = "def add(a, b):\n    return a - b\n"
FIXED_MODULE = "def add(a, b):\n    return a + b\n"
GRADER_TEST = (
    "from solution import add\n\n\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
    "    assert add(-1, 1) == 0\n"
)


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="hyp-test0001",
        title="Test intervention improves pass rate",
        claim="Appending the intervention raises task pass rate.",
        rationale="test",
        assumptions=[],
        evidence_refs=[],
        test_plan=TestPlan(experiment="A/B", metrics=["pass_rate"], success_condition="delta>0"),
        risks=[],
        origin="test",
    )


def _make_suite(root: Path, task_ids: list[str]) -> Path:
    suite = root / "suite"
    for task_id in task_ids:
        task_dir = suite / task_id
        (task_dir / "workspace").mkdir(parents=True)
        (task_dir / "grader").mkdir()
        (task_dir / "task.json").write_text(
            json.dumps(
                {
                    "id": task_id,
                    "title": task_id,
                    "prompt": "Fix add() in solution.py so it adds.",
                    "timeout_seconds": 60,
                }
            ),
            encoding="utf-8",
        )
        (task_dir / "workspace" / "solution.py").write_text(BROKEN_MODULE, encoding="utf-8")
        (task_dir / "grader" / "test_grader.py").write_text(GRADER_TEST, encoding="utf-8")
    return suite


def _fixing_script(task_ids: list[str], arm: str = "candidate") -> dict:
    return {
        task_id: {arm: {"files": {"solution.py": FIXED_MODULE}}}
        for task_id in task_ids
    }


def _protocol(suite: Path, tasks, **overrides):
    defaults = dict(
        state_path="state.json",
        hypothesis=_hypothesis(),
        intervention="Always re-read the diff before finishing.",
        task_suite=str(suite),
        tasks=tasks,
        trials_per_task=3,
        seed=11,
        executor="deterministic",
    )
    defaults.update(overrides)
    return build_protocol(**defaults)


def test_load_agent_tasks_validates_structure(tmp_path):
    suite = _make_suite(tmp_path, ["task-a", "task-b"])

    tasks = load_agent_tasks(suite)
    assert [task.id for task in tasks] == ["task-a", "task-b"]

    filtered = load_agent_tasks(suite, ["task-b"])
    assert [task.id for task in filtered] == ["task-b"]

    with pytest.raises(ExperimentConfigError):
        load_agent_tasks(suite, ["task-missing"])

    (suite / "task-a" / "grader" / "test_grader.py").unlink()
    with pytest.raises(ExperimentConfigError):
        load_agent_tasks(suite)


def test_load_agent_tasks_rejects_id_mismatch(tmp_path):
    suite = _make_suite(tmp_path, ["task-a"])
    task_json = suite / "task-a" / "task.json"
    data = json.loads(task_json.read_text())
    data["id"] = "other-name"
    task_json.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ExperimentConfigError):
        load_agent_tasks(suite)


def test_one_sided_binomial_known_values():
    assert _one_sided_binomial(0, 0) == 1.0
    assert _one_sided_binomial(5, 6) == pytest.approx(7 / 64)
    assert _one_sided_binomial(7, 7) == pytest.approx(1 / 128)
    assert _one_sided_binomial(0, 4) == 1.0


def _arm(task_id: str, trial: int, arm: str, passed: bool) -> TrialArmResult:
    return TrialArmResult(
        task_id=task_id,
        trial=trial,
        arm=arm,
        passed=passed,
        agent_status="completed",
        duration_seconds=1.0,
        num_turns=2.0,
        cost_usd=0.01,
    )


def test_stats_and_verdict_supported():
    arms = []
    for task_id in ("t1", "t2"):
        for trial in (1, 2, 3):
            arms.append(_arm(task_id, trial, "baseline", False))
            arms.append(_arm(task_id, trial, "candidate", True))

    stats = compute_experiment_stats(arms, seed=1, bootstrap_iterations=500)
    assert stats["n_pairs"] == 6.0
    assert stats["pass_rate_delta"] == pytest.approx(1.0)
    assert stats["discordant_pairs"] == 6.0
    assert stats["mcnemar_p_one_sided"] == pytest.approx(1 / 64)
    assert stats["delta_ci95_low"] == pytest.approx(1.0)
    assert stats["delta_ci95_high"] == pytest.approx(1.0)
    assert stats["tasks_candidate_better"] == 2.0
    assert decide_verdict(stats, alpha=0.05, min_discordant_pairs=3) == "supported"


def test_stats_and_verdict_refuted():
    arms = []
    for task_id in ("t1", "t2"):
        for trial in (1, 2, 3):
            arms.append(_arm(task_id, trial, "baseline", True))
            arms.append(_arm(task_id, trial, "candidate", False))

    stats = compute_experiment_stats(arms, seed=1, bootstrap_iterations=200)
    assert stats["pass_rate_delta"] == pytest.approx(-1.0)
    assert stats["mcnemar_p_regression"] == pytest.approx(1 / 64)
    assert decide_verdict(stats, alpha=0.05, min_discordant_pairs=3) == "refuted"


def test_verdict_inconclusive_below_min_discordant():
    arms = [
        _arm("t1", 1, "baseline", False),
        _arm("t1", 1, "candidate", True),
        _arm("t1", 2, "baseline", True),
        _arm("t1", 2, "candidate", True),
    ]
    stats = compute_experiment_stats(arms, seed=1, bootstrap_iterations=100)
    assert stats["discordant_pairs"] == 1.0
    assert decide_verdict(stats, alpha=0.05, min_discordant_pairs=3) == "inconclusive"


def test_verdict_inconclusive_when_empty():
    assert decide_verdict(compute_experiment_stats([], seed=1)) == "inconclusive"


def test_grade_workspace_pass_and_fail(tmp_path):
    suite = _make_suite(tmp_path, ["task-a"])
    task = load_agent_tasks(suite)[0]

    workspace = tmp_path / "graded-fail"
    workspace.mkdir()
    (workspace / "solution.py").write_text(BROKEN_MODULE, encoding="utf-8")
    passed, tail = grade_workspace(workspace, task.grader_dir())
    assert passed is False
    assert "failed" in tail or "error" in tail.lower()

    workspace_ok = tmp_path / "graded-pass"
    workspace_ok.mkdir()
    (workspace_ok / "solution.py").write_text(FIXED_MODULE, encoding="utf-8")
    passed_ok, _ = grade_workspace(workspace_ok, task.grader_dir())
    assert passed_ok is True


def test_deterministic_experiment_end_to_end(tmp_path):
    task_ids = ["task-a", "task-b"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    protocol = _protocol(suite, tasks)
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)
    executor = DeterministicAgentExecutor(script=_fixing_script(task_ids))

    result = run_experiment(protocol, tasks, executor, out_dir)

    assert result.status == "complete"
    assert result.verdict == "supported"
    assert result.stats["n_pairs"] == 6.0
    assert (out_dir / "experiment.json").exists()
    assert (out_dir / "experiment-report.md").exists()
    arm_dir = out_dir / "trials" / "task-a" / "trial-1" / "candidate"
    assert (arm_dir / "agent-output.json").exists()
    assert "modified: solution.py" in (arm_dir / "workspace-diff.txt").read_text()
    assert (arm_dir / "grader-output.txt").exists()
    baseline_diff = (out_dir / "trials" / "task-a" / "trial-1" / "baseline" / "workspace-diff.txt").read_text()
    assert "no changes" in baseline_diff

    benchmark = benchmark_result_from_experiment(protocol, result)
    assert benchmark.provenance == MEASURED_PROVENANCE
    assert benchmark.hypothesis_id == "hyp-test0001"
    assert benchmark.verdict == "supported"
    assert benchmark.success is True
    assert benchmark.deltas["pass_rate"] == pytest.approx(1.0)
    assert benchmark.candidate_metrics["cost"] == 0.0

    report = (out_dir / "experiment-report.md").read_text()
    assert "pre-registered" in report
    assert "trusted_local" in report


def test_experiment_reruns_are_deterministic(tmp_path):
    task_ids = ["task-a", "task-b"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    script = _fixing_script(task_ids)

    results = []
    for label in ("one", "two"):
        protocol = _protocol(suite, tasks)
        out_dir = tmp_path / f"experiment-{label}"
        protocol = pre_register_protocol(protocol, out_dir)
        result = run_experiment(
            protocol, tasks, DeterministicAgentExecutor(script=script), out_dir
        )
        results.append(result.stats)

    assert results[0] == results[1]


def _spec(workspace, *, arm="candidate", system_append="Verify before finishing.", prompt="Fix the bug.", timeout=120.0):
    return TrialSpec(
        request_id=f"task-a-trial1-{arm}",
        task_id="task-a",
        trial=1,
        arm=arm,
        prompt=prompt,
        system_append=system_append,
        workspace=str(workspace),
        timeout_seconds=timeout,
    )


class _CostlyExecutor:
    def run_batch(self, specs):
        return [
            AgentInvocation(
                status="completed",
                duration_seconds=1.0,
                num_turns=1.0,
                cost_usd=5.0,
                raw_output="{}",
            )
            for _ in specs
        ]


def test_experiment_stops_on_cost_budget(tmp_path):
    suite = _make_suite(tmp_path, ["task-a"])
    tasks = load_agent_tasks(suite)
    protocol = _protocol(suite, tasks, cost_budget_usd=4.0)
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)

    result = run_experiment(protocol, tasks, _CostlyExecutor(), out_dir)

    assert result.status == "incomplete"
    assert result.verdict == "incomplete"
    # Budget is enforced between chunks: the first pair (2 arms) completes,
    # then the run stops before the next chunk starts.
    assert len(result.trial_arms) == 2
    assert any("cost budget" in note for note in result.notes)


def _fake_runner(record: dict, stdout: str = "", returncode: int = 0):
    def runner(argv, stdin_text, timeout, env, cwd):
        record["argv"] = argv
        record["stdin"] = stdin_text
        record["timeout"] = timeout
        record["env"] = env
        record["cwd"] = cwd
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return runner


def _success_payload() -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 2000,
            "num_turns": 4,
            "result": "done",
            "total_cost_usd": 0.0125,
        }
    )


def test_claude_cli_executor_argv_env_and_parsing(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "harness-proxy-key")
    record: dict = {}
    executor = ClaudeCliAgentExecutor(
        model="claude-haiku-4-5",
        max_turns=9,
        agent_auth="login",
        runner=_fake_runner(record, stdout=_success_payload()),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()

    invocation = executor.run_trial(_spec(workspace))

    argv = record["argv"]
    assert "-p" in argv
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert argv[argv.index("--max-turns") + 1] == "9"
    assert argv[argv.index("--append-system-prompt") + 1] == "Verify before finishing."
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--allowedTools" in argv and "--disallowedTools" in argv
    assert record["stdin"] == "Fix the bug."
    assert record["cwd"] == str(workspace)
    assert "ANTHROPIC_API_KEY" not in record["env"]
    assert invocation.status == "completed"
    assert invocation.num_turns == 4.0
    assert invocation.cost_usd == pytest.approx(0.0125)
    assert invocation.duration_seconds == pytest.approx(2.0)


def test_claude_cli_executor_omits_append_for_baseline(tmp_path):
    record: dict = {}
    executor = ClaudeCliAgentExecutor(
        model="claude-haiku-4-5",
        runner=_fake_runner(record, stdout=_success_payload()),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()

    executor.run_trial(_spec(workspace, arm="baseline", system_append="", timeout=60.0))

    assert "--append-system-prompt" not in record["argv"]


def test_claude_cli_executor_api_key_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "harness-proxy-key")
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-real-file-key\n", encoding="utf-8")
    record: dict = {}
    executor = ClaudeCliAgentExecutor(
        model="claude-haiku-4-5",
        agent_auth="api-key",
        env_file=env_file,
        runner=_fake_runner(record, stdout=_success_payload()),
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()

    executor.run_trial(_spec(workspace, arm="baseline", system_append="", prompt="Fix.", timeout=60.0))

    assert record["env"]["ANTHROPIC_API_KEY"] == "sk-real-file-key"


def test_claude_cli_executor_requires_key_for_api_key_mode(tmp_path):
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")

    with pytest.raises(ExperimentConfigError):
        ClaudeCliAgentExecutor(
            model="claude-haiku-4-5",
            agent_auth="api-key",
            env_file=empty_env,
        )


def test_claude_cli_executor_timeout_and_abort(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    def timeout_runner(argv, stdin_text, timeout, env, cwd):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    executor = ClaudeCliAgentExecutor(
        model="claude-haiku-4-5", runner=timeout_runner
    )
    invocation = executor.run_trial(_spec(workspace, arm="baseline", system_append="", timeout=1.0))
    assert invocation.status == "timeout"

    record: dict = {}
    auth_fail = ClaudeCliAgentExecutor(
        model="claude-haiku-4-5",
        runner=_fake_runner(
            record,
            stdout='{"is_error": true, "result": "authentication_error: run /login"}',
            returncode=1,
        ),
    )
    with pytest.raises(ExperimentAbort):
        auth_fail.run_trial(_spec(workspace, arm="baseline", system_append="", timeout=1.0))


def test_host_agent_executor_answers_from_bridge(tmp_path):
    bridge = tmp_path / "agent-bridge"
    (bridge / "responses").mkdir(parents=True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    spec = _spec(workspace, timeout=5.0)
    (bridge / "responses" / f"{spec.request_id}.json").write_text(
        json.dumps(
            {
                "id": spec.request_id,
                "status": "completed",
                "duration_seconds": 12.5,
                "num_turns": 6,
                "cost_usd": 0.0,
            }
        ),
        encoding="utf-8",
    )
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=2.0, poll_seconds=0.02)

    invocations = executor.run_batch([spec])

    assert invocations[0].status == "completed"
    assert invocations[0].duration_seconds == pytest.approx(12.5)
    assert invocations[0].num_turns == 6.0
    # The answered request is removed; the request payload carried the trial.
    assert not (bridge / "requests" / f"{spec.request_id}.json").exists()


def test_host_agent_executor_request_payload_is_complete(tmp_path):
    bridge = tmp_path / "agent-bridge"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    spec = _spec(workspace, timeout=0.2)
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=0.1, poll_seconds=0.02)

    invocations = executor.run_batch([spec])

    # Unanswered: times out, but the request must have been written complete.
    assert invocations[0].status == "timeout"
    request_path = bridge / "requests" / f"{spec.request_id}.json"
    assert not request_path.exists()  # cleaned up after the deadline


def test_host_agent_executor_abandons_after_unanswered_batches(tmp_path):
    bridge = tmp_path / "agent-bridge"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    executor = HostAgentTrialExecutor(
        bridge, response_margin_seconds=0.05, poll_seconds=0.02, abandon_after_batches=2
    )
    spec = _spec(workspace, timeout=0.05)

    first = executor.run_batch([spec])
    assert first[0].status == "timeout"
    with pytest.raises(ExperimentAbort):
        executor.run_batch([spec])


def test_host_agent_executor_stop_file_aborts(tmp_path):
    bridge = tmp_path / "agent-bridge"
    bridge.mkdir(parents=True)
    (bridge / "stop").write_text("", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=5.0)

    with pytest.raises(ExperimentAbort):
        executor.run_batch([_spec(workspace, timeout=5.0)])


def test_host_agent_executor_error_and_unknown_status(tmp_path):
    bridge = tmp_path / "agent-bridge"
    (bridge / "responses").mkdir(parents=True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    error_spec = _spec(workspace, arm="baseline", system_append="", timeout=5.0)
    unknown_spec = _spec(workspace, timeout=5.0)
    (bridge / "responses" / f"{error_spec.request_id}.json").write_text(
        json.dumps({"id": error_spec.request_id, "error": "subagent crashed"}),
        encoding="utf-8",
    )
    (bridge / "responses" / f"{unknown_spec.request_id}.json").write_text(
        json.dumps({"id": unknown_spec.request_id, "status": "finished-i-guess"}),
        encoding="utf-8",
    )
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=2.0, poll_seconds=0.02)

    invocations = executor.run_batch([error_spec, unknown_spec])

    assert invocations[0].status == "error"
    assert "subagent crashed" in invocations[0].detail
    assert invocations[1].status == "error"
    assert "unrecognized bridge status" in invocations[1].detail


def test_run_experiment_with_host_agent_prewritten_responses(tmp_path):
    task_ids = ["task-a"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    protocol = _protocol(
        suite, tasks, executor="host-agent", trials_per_task=1, trial_concurrency=2
    )
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)
    bridge = out_dir / "agent-bridge"
    (bridge / "responses").mkdir(parents=True)
    for arm in ("baseline", "candidate"):
        (bridge / "responses" / f"task-a-trial1-{arm}.json").write_text(
            json.dumps({"id": f"task-a-trial1-{arm}", "status": "completed"}),
            encoding="utf-8",
        )
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=2.0, poll_seconds=0.02)

    result = run_experiment(protocol, tasks, executor, out_dir)

    assert result.status == "complete"
    assert result.stats["n_pairs"] == 1.0
    # Neither arm edited the workspace, so both fail the grader.
    assert result.stats["baseline_pass_rate"] == 0.0
    assert result.stats["candidate_pass_rate"] == 0.0
    assert result.verdict == "inconclusive"


class _SlowFixingExecutor:
    """Fixes the task but reports more wall time than the trial budget."""

    def __init__(self, script):
        self._inner = DeterministicAgentExecutor(script=script)

    def run_batch(self, specs):
        return [
            AgentInvocation(
                status="completed",
                duration_seconds=spec.timeout_seconds + 30.0,
                num_turns=3.0,
                cost_usd=0.0,
                raw_output="{}",
            )
            for spec in specs
            if self._inner.run_trial(spec)
        ]


def test_overtime_arm_fails_even_when_graders_pass(tmp_path):
    task_ids = ["task-a"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    protocol = _protocol(suite, tasks, trials_per_task=1)
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)

    result = run_experiment(
        protocol, tasks, _SlowFixingExecutor(_fixing_script(task_ids, arm="candidate")), out_dir
    )

    candidate = next(item for item in result.trial_arms if item.arm == "candidate")
    assert candidate.overtime is True
    assert candidate.passed is False  # graders passed, but the budget rule flips it
    baseline = next(item for item in result.trial_arms if item.arm == "baseline")
    assert baseline.overtime is True


def test_host_agent_timeout_arm_is_marked_overtime(tmp_path):
    # A synthesized bridge timeout reports duration == budget; without the
    # status check the strict `>` overtime comparison would let a fix that
    # landed after the deadline pass.
    task_ids = ["task-a"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    protocol = _protocol(suite, tasks, executor="host-agent", trials_per_task=1)
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)
    bridge = out_dir / "agent-bridge"
    (bridge / "responses").mkdir(parents=True)
    # Answer only the baseline; leave the candidate unanswered so it times out.
    (bridge / "responses" / "task-a-trial1-baseline.json").write_text(
        json.dumps({"id": "task-a-trial1-baseline", "status": "completed"}),
        encoding="utf-8",
    )
    # Even if a timed-out arm's workspace happened to satisfy the grader, the
    # overtime rule must fail it. Pre-fix the candidate workspace so graders pass.
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=0.1, poll_seconds=0.02)
    (out_dir / "trials").mkdir(parents=True, exist_ok=True)

    result = run_experiment(protocol, tasks, executor, out_dir)

    candidate = next(item for item in result.trial_arms if item.arm == "candidate")
    assert candidate.agent_status == "timeout"
    assert candidate.overtime is True
    assert candidate.passed is False


def test_run_experiment_purges_stale_bridge_responses(tmp_path):
    task_ids = ["task-a"]
    suite = _make_suite(tmp_path, task_ids)
    tasks = load_agent_tasks(suite)
    protocol = _protocol(suite, tasks, executor="host-agent", trials_per_task=1)
    out_dir = tmp_path / "experiment"
    protocol = pre_register_protocol(protocol, out_dir)
    bridge = out_dir / "agent-bridge"
    (bridge / "responses").mkdir(parents=True)
    # A stale response and stop file from a prior interrupted run.
    (bridge / "responses" / "task-a-trial1-baseline.json").write_text(
        json.dumps({"id": "task-a-trial1-baseline", "status": "completed"}),
        encoding="utf-8",
    )
    (bridge / "stop").write_text("", encoding="utf-8")

    # The purge runs at start; with no live answerer the run times out fast
    # rather than instantly consuming the stale response as a fresh result.
    executor = HostAgentTrialExecutor(bridge, response_margin_seconds=0.1, poll_seconds=0.02)
    result = run_experiment(protocol, tasks, executor, out_dir)

    assert not (bridge / "stop").exists()
    baseline = next(item for item in result.trial_arms if item.arm == "baseline")
    # Stale "completed" was purged, so the arm actually timed out.
    assert baseline.agent_status == "timeout"


def test_grade_workspace_ignores_agent_written_pytest_config(tmp_path):
    suite = _make_suite(tmp_path, ["task-a"])
    task = load_agent_tasks(suite)[0]

    # Broken solution + an agent-planted conftest.py that skips all tests and a
    # pyproject.toml that would force --collect-only. The grader must still fail.
    workspace = tmp_path / "sabotaged"
    workspace.mkdir()
    (workspace / "solution.py").write_text(BROKEN_MODULE, encoding="utf-8")
    (workspace / "conftest.py").write_text(
        "import pytest\n\n\n"
        "def pytest_collection_modifyitems(config, items):\n"
        "    for item in items:\n"
        "        item.add_marker(pytest.mark.skip(reason='sabotage'))\n",
        encoding="utf-8",
    )
    (workspace / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = \"--collect-only\"\n", encoding="utf-8"
    )

    passed, _tail = grade_workspace(workspace, task.grader_dir())
    assert passed is False

    # The correct solution still passes despite the same planted config.
    fixed = tmp_path / "fixed"
    fixed.mkdir()
    (fixed / "solution.py").write_text(FIXED_MODULE, encoding="utf-8")
    (fixed / "conftest.py").write_text("# noop\n", encoding="utf-8")
    passed_ok, _ = grade_workspace(fixed, task.grader_dir())
    assert passed_ok is True


def test_protocol_preregistration_conflict(tmp_path):
    suite = _make_suite(tmp_path, ["task-a"])
    tasks = load_agent_tasks(suite)
    out_dir = tmp_path / "experiment"

    first = pre_register_protocol(_protocol(suite, tasks), out_dir)
    again = pre_register_protocol(_protocol(suite, tasks), out_dir)
    assert again.id == first.id
    assert again.created_at == first.created_at

    with pytest.raises(ExperimentConfigError):
        pre_register_protocol(
            _protocol(suite, tasks, intervention="A different intervention."),
            out_dir,
        )


def test_benchmark_result_backward_compat_loading():
    legacy = {
        "id": "bench-1234",
        "name": "legacy",
        "source": "fixture.json",
        "baseline_metrics": {"pass_rate": 0.5},
        "candidate_metrics": {"pass_rate": 0.7},
        "deltas": {"pass_rate": 0.2},
        "success": True,
    }
    result = BenchmarkResult.from_dict(legacy)
    assert result.provenance == ""
    assert result.hypothesis_id == ""
    assert result.verdict == ""
    assert result.stats == {}


def test_cli_validate_deterministic_end_to_end(tmp_path):
    run_dir = tmp_path / "run"
    assert main(["run", "Find testable ideas to improve LLM coding agents", "--out", str(run_dir)]) == 0
    state = json.loads((run_dir / "state.json").read_text())
    hypothesis_id = state["hypotheses"][0]["id"]

    task_ids = ["task-a", "task-b"]
    suite = _make_suite(tmp_path, task_ids)
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(_fixing_script(task_ids)), encoding="utf-8")
    out_dir = tmp_path / "experiment"

    exit_code = main(
        [
            "validate",
            str(run_dir / "state.json"),
            "--hypothesis",
            hypothesis_id,
            "--intervention",
            "Re-run the visible tests before declaring done.",
            "--tasks",
            str(suite),
            "--executor",
            "deterministic",
            "--executor-script",
            str(script_path),
            "--trials",
            "3",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "protocol.json").exists()
    assert (out_dir / "experiment.json").exists()
    updated = json.loads((run_dir / "state.json").read_text())
    measured = [
        item
        for item in updated["benchmark_results"]
        if item.get("provenance") == MEASURED_PROVENANCE
    ]
    assert len(measured) == 1
    assert measured[0]["hypothesis_id"] == hypothesis_id
    assert measured[0]["verdict"] == "supported"
    report = (run_dir / "report.md").read_text()
    assert "executed experiment" in report

    assert main(["findings", str(run_dir / "state.json")]) == 0
    findings = (run_dir / "findings.md").read_text()
    if hypothesis_id in findings:
        assert "Measured result:" in findings


def test_cli_validate_dry_run_only_registers(tmp_path):
    run_dir = tmp_path / "run"
    assert main(["run", "Find testable ideas to improve LLM coding agents", "--out", str(run_dir)]) == 0
    state = json.loads((run_dir / "state.json").read_text())
    hypothesis_id = state["hypotheses"][0]["id"]
    suite = _make_suite(tmp_path, ["task-a"])
    out_dir = tmp_path / "experiment"

    exit_code = main(
        [
            "validate",
            str(run_dir / "state.json"),
            "--hypothesis",
            hypothesis_id,
            "--intervention",
            "Check twice.",
            "--tasks",
            str(suite),
            "--executor",
            "deterministic",
            "--out",
            str(out_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert (out_dir / "protocol.json").exists()
    assert not (out_dir / "experiment.json").exists()


def test_cli_validate_refuses_completed_out_dir(tmp_path):
    run_dir = tmp_path / "run"
    assert main(["run", "Find testable ideas to improve LLM coding agents", "--out", str(run_dir)]) == 0
    state = json.loads((run_dir / "state.json").read_text())
    hypothesis_id = state["hypotheses"][0]["id"]
    suite = _make_suite(tmp_path, ["task-a"])
    out_dir = tmp_path / "experiment"
    argv = [
        "validate",
        str(run_dir / "state.json"),
        "--hypothesis",
        hypothesis_id,
        "--intervention",
        "Check twice.",
        "--tasks",
        str(suite),
        "--executor",
        "deterministic",
        "--out",
        str(out_dir),
    ]
    assert main(argv) == 0

    with pytest.raises(ExperimentConfigError):
        main(argv)
