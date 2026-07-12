"""Measured validation: pre-registered baseline-vs-candidate agent experiments.

This module executes a hypothesis as a controlled experiment on a real coding
agent. Both arms solve the same held-out-graded tasks; the only difference is
the candidate arm's appended system prompt (the intervention derived from the
hypothesis). Results become a ``BenchmarkResult`` with ``measured`` provenance,
in contrast to asserted benchmark fixtures.

Execution policy is ``trusted_local``: trials run as local subprocesses in
temporary workspace copies and no sandbox isolation is claimed, matching the
honesty contract of ``prospective-validation-run``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_scientist.llm import (
    BRIDGE_STOP_FILENAME,
    CLAUDE_CLI_SANITIZED_ENV_VARS,
    DEFAULT_BRIDGE_POLL_SECONDS,
    DEFAULT_CLAUDE_CLI_BINARY,
    read_dotenv,
    _atomic_write_json,
    _read_json_object,
    _resolve_claude_binary,
)
from code_scientist.models import BenchmarkResult, Hypothesis, stable_id


EXECUTOR_CHOICES = ("deterministic", "claude-cli", "host-agent")
AGENT_AUTH_CHOICES = ("login", "api-key")
MEASURED_PROVENANCE = "measured:agent-experiment"

DEFAULT_TRIALS_PER_TASK = 3
DEFAULT_SEED = 7
DEFAULT_MAX_TURNS = 15
DEFAULT_TRIAL_TIMEOUT_SECONDS = 300.0
DEFAULT_GRADING_TIMEOUT_SECONDS = 120.0
DEFAULT_ALPHA = 0.05
DEFAULT_MIN_DISCORDANT_PAIRS = 3
DEFAULT_COST_BUDGET_USD = 10.0
DEFAULT_BOOTSTRAP_ITERATIONS = 10_000
DEFAULT_ALLOWED_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
DEFAULT_DISALLOWED_TOOLS = "WebSearch,WebFetch,Task"

_ARM_BASELINE = "baseline"
_ARM_CANDIDATE = "candidate"
_DIFF_MAX_BYTES = 65536

# Output markers that make every later trial pointless: fail the whole
# experiment fast instead of burning the remaining budget on identical errors.
_ABORT_MARKERS = (
    "authentication_error",
    "invalid authentication credentials",
    "please run /login",
    "credit balance is too low",
)


class ExperimentConfigError(ValueError):
    """Invalid task suite, protocol, or executor configuration."""


class ExperimentAbort(RuntimeError):
    """The run cannot produce meaningful further trials (auth/credit failure)."""


AgentCommandRunner = Callable[
    [list[str], str, float, dict[str, str] | None, str],
    "subprocess.CompletedProcess[str]",
]


def _agent_subprocess_runner(
    argv: list[str],
    stdin_text: str,
    timeout: float,
    env: dict[str, str] | None,
    cwd: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
        check=False,
    )


# ---------------------------------------------------------------------------
# Task suite


@dataclass(frozen=True)
class AgentTask:
    id: str
    title: str
    prompt: str
    timeout_seconds: float
    path: str

    def workspace_dir(self) -> Path:
        return Path(self.path) / "workspace"

    def grader_dir(self) -> Path:
        return Path(self.path) / "grader"


def load_agent_tasks(suite_dir: str | Path, task_ids: list[str] | None = None) -> list[AgentTask]:
    suite_path = Path(suite_dir)
    if not suite_path.is_dir():
        raise ExperimentConfigError(f"Task suite directory not found: {suite_path}")

    tasks: list[AgentTask] = []
    for entry in sorted(suite_path.iterdir()):
        if not entry.is_dir() or not (entry / "task.json").exists():
            continue
        tasks.append(_load_agent_task(entry))

    if not tasks:
        raise ExperimentConfigError(f"No tasks found under {suite_path}")

    if task_ids:
        by_id = {task.id: task for task in tasks}
        missing = [task_id for task_id in task_ids if task_id not in by_id]
        if missing:
            raise ExperimentConfigError(f"Unknown task ids: {', '.join(missing)}")
        tasks = [by_id[task_id] for task_id in task_ids]
    return tasks


def _load_agent_task(task_dir: Path) -> AgentTask:
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ExperimentConfigError(f"task.json must be a JSON object: {task_dir}")
    task_id = str(data.get("id") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not task_id or not prompt:
        raise ExperimentConfigError(f"task.json requires non-empty id and prompt: {task_dir}")
    if task_id != task_dir.name:
        raise ExperimentConfigError(
            f"task.json id {task_id!r} does not match directory name {task_dir.name!r}"
        )
    workspace = task_dir / "workspace"
    grader = task_dir / "grader"
    if not workspace.is_dir():
        raise ExperimentConfigError(f"Task {task_id} is missing workspace/")
    if not grader.is_dir() or not list(grader.glob("test_*.py")):
        raise ExperimentConfigError(f"Task {task_id} is missing grader/ test files")
    return AgentTask(
        id=task_id,
        title=str(data.get("title") or task_id),
        prompt=prompt,
        timeout_seconds=float(data.get("timeout_seconds") or DEFAULT_TRIAL_TIMEOUT_SECONDS),
        path=str(task_dir),
    )


# ---------------------------------------------------------------------------
# Protocol (pre-registration)


@dataclass(frozen=True)
class ExperimentProtocol:
    id: str
    created_at: str
    state_path: str
    hypothesis_id: str
    hypothesis_title: str
    hypothesis_claim: str
    baseline_description: str
    intervention: str
    task_suite: str
    task_ids: list[str]
    trials_per_task: int
    seed: int
    executor: str
    model: str
    max_turns: int
    trial_timeout_seconds: float
    allowed_tools: str
    disallowed_tools: str
    agent_auth: str
    alpha: float
    min_discordant_pairs: int
    cost_budget_usd: float
    execution_policy: str = "trusted_local"
    direction: str = "candidate_gt_baseline"
    trial_concurrency: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentProtocol:
        copied = dict(data)
        copied.setdefault("execution_policy", "trusted_local")
        copied.setdefault("direction", "candidate_gt_baseline")
        copied.setdefault("trial_concurrency", 1)
        return cls(**copied)

    def content_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_protocol(
    *,
    state_path: str,
    hypothesis: Hypothesis,
    intervention: str,
    task_suite: str,
    tasks: list[AgentTask],
    trials_per_task: int = DEFAULT_TRIALS_PER_TASK,
    seed: int = DEFAULT_SEED,
    executor: str = "deterministic",
    model: str = "",
    max_turns: int = DEFAULT_MAX_TURNS,
    trial_timeout_seconds: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
    disallowed_tools: str = DEFAULT_DISALLOWED_TOOLS,
    agent_auth: str = "login",
    alpha: float = DEFAULT_ALPHA,
    min_discordant_pairs: int = DEFAULT_MIN_DISCORDANT_PAIRS,
    cost_budget_usd: float = DEFAULT_COST_BUDGET_USD,
    trial_concurrency: int = 1,
) -> ExperimentProtocol:
    cleaned_intervention = intervention.strip()
    if not cleaned_intervention:
        raise ExperimentConfigError(
            "An experiment requires a non-empty intervention (the candidate arm's appended system prompt)."
        )
    if executor not in EXECUTOR_CHOICES:
        raise ExperimentConfigError(f"executor must be one of {', '.join(EXECUTOR_CHOICES)}")
    if agent_auth not in AGENT_AUTH_CHOICES:
        raise ExperimentConfigError(f"agent-auth must be one of {', '.join(AGENT_AUTH_CHOICES)}")
    if trials_per_task < 1:
        raise ExperimentConfigError("trials-per-task must be at least 1.")
    if not 0.0 < alpha < 1.0:
        raise ExperimentConfigError("alpha must be between 0 and 1.")
    created_at = datetime.now(timezone.utc).isoformat()
    experiment_id = stable_id(
        "exp",
        f"{hypothesis.id}:{cleaned_intervention}:{[task.id for task in tasks]}:{trials_per_task}:{seed}:{created_at}",
    )
    return ExperimentProtocol(
        id=experiment_id,
        created_at=created_at,
        state_path=str(state_path),
        hypothesis_id=hypothesis.id,
        hypothesis_title=hypothesis.title,
        hypothesis_claim=hypothesis.claim,
        baseline_description="Agent defaults: identical prompt, model, tools, and limits with no appended system prompt.",
        intervention=cleaned_intervention,
        task_suite=str(task_suite),
        task_ids=[task.id for task in tasks],
        trials_per_task=int(trials_per_task),
        seed=int(seed),
        executor=executor,
        model=model,
        max_turns=int(max_turns),
        trial_timeout_seconds=float(trial_timeout_seconds),
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        agent_auth=agent_auth,
        alpha=float(alpha),
        min_discordant_pairs=int(min_discordant_pairs),
        cost_budget_usd=float(cost_budget_usd),
        trial_concurrency=max(1, int(trial_concurrency)),
    )


def pre_register_protocol(protocol: ExperimentProtocol, out_dir: str | Path) -> ExperimentProtocol:
    """Write protocol.json before any trial runs.

    If a protocol is already registered in ``out_dir`` it wins, provided it
    matches the requested protocol on every field except id/created_at (which
    capture the registration moment). A mismatch is an error: results must
    never silently run under a different protocol than the registered one.
    """

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    protocol_path = out_path / "protocol.json"
    if protocol_path.exists():
        existing = ExperimentProtocol.from_dict(
            json.loads(protocol_path.read_text(encoding="utf-8"))
        )
        requested_view = replace(protocol, id=existing.id, created_at=existing.created_at)
        if requested_view != existing:
            raise ExperimentConfigError(
                f"A different protocol is already registered at {protocol_path}; "
                "use a fresh --out directory or matching arguments."
            )
        return existing
    protocol_path.write_text(
        json.dumps(protocol.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return protocol


# ---------------------------------------------------------------------------
# Executors


@dataclass(frozen=True)
class AgentInvocation:
    status: str  # completed | max-turns | timeout | error
    duration_seconds: float
    num_turns: float
    cost_usd: float
    raw_output: str
    detail: str = ""


@dataclass(frozen=True)
class TrialSpec:
    """One arm of one paired trial, as handed to an executor."""

    request_id: str
    task_id: str
    trial: int
    arm: str
    prompt: str
    system_append: str
    workspace: str
    timeout_seconds: float


def _sequential_run_batch(executor: Any, specs: list[TrialSpec]) -> list[AgentInvocation]:
    return [executor.run_trial(spec) for spec in specs]


class DeterministicAgentExecutor:
    """Scripted executor for tests and offline demos.

    The script maps task id -> arm -> {"files": {relative_path: content}};
    listed files are written into the workspace as if an agent edited them.
    Unscripted (task, arm) combinations leave the workspace untouched. Like
    every deterministic path in this project, outcomes are scaffolding, not
    measurements of a real agent.
    """

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}

    def run_trial(self, spec: TrialSpec) -> AgentInvocation:
        entry = self.script.get(spec.task_id, {}).get(spec.arm)
        written: list[str] = []
        if isinstance(entry, dict):
            files = entry.get("files")
            if isinstance(files, dict):
                for relative, content in files.items():
                    target = Path(spec.workspace) / str(relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(content), encoding="utf-8")
                    written.append(str(relative))
        return AgentInvocation(
            status="completed",
            duration_seconds=0.0,
            num_turns=1.0,
            cost_usd=0.0,
            raw_output=json.dumps({"deterministic": True, "files_written": written}),
        )

    def run_batch(self, specs: list[TrialSpec]) -> list[AgentInvocation]:
        return _sequential_run_batch(self, specs)


class ClaudeCliAgentExecutor:
    """Runs one trial arm through headless Claude Code (`claude -p`).

    Auth modes:
    - ``login``: strip session auth/endpoint overrides so the child process
      uses the local CLI login (same gotcha as the claude-cli provider).
    - ``api-key``: strip the same variables, then inject the key read from the
      env file. Environment keys are deliberately not trusted here — inside a
      hosted session they can point at a harness proxy that rejects direct use.
    """

    def __init__(
        self,
        *,
        model: str,
        max_turns: int = DEFAULT_MAX_TURNS,
        allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
        disallowed_tools: str = DEFAULT_DISALLOWED_TOOLS,
        agent_auth: str = "login",
        env_file: str | Path = ".env",
        binary: str = DEFAULT_CLAUDE_CLI_BINARY,
        runner: AgentCommandRunner | None = None,
    ) -> None:
        if not model.strip():
            raise ExperimentConfigError("The claude-cli executor requires an explicit --model.")
        if agent_auth not in AGENT_AUTH_CHOICES:
            raise ExperimentConfigError(f"agent-auth must be one of {', '.join(AGENT_AUTH_CHOICES)}")
        self.model = model.strip()
        self.max_turns = int(max_turns)
        self.allowed_tools = allowed_tools.strip()
        self.disallowed_tools = disallowed_tools.strip()
        self.agent_auth = agent_auth
        self.binary = _resolve_claude_binary(binary)
        self._runner = runner or _agent_subprocess_runner
        self._api_key = ""
        if agent_auth == "api-key":
            self._api_key = str(read_dotenv(env_file).get("ANTHROPIC_API_KEY") or "").strip()
            if not self._api_key:
                raise ExperimentConfigError(
                    f"agent-auth api-key requires ANTHROPIC_API_KEY in {env_file}."
                )

    def _child_env(self) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in CLAUDE_CLI_SANITIZED_ENV_VARS
        }
        if self.agent_auth == "api-key":
            env["ANTHROPIC_API_KEY"] = self._api_key
        return env

    def run_trial(self, spec: TrialSpec) -> AgentInvocation:
        argv = [
            self.binary,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--max-turns",
            str(self.max_turns),
        ]
        if self.allowed_tools:
            argv.extend(["--allowedTools", self.allowed_tools])
        if self.disallowed_tools:
            argv.extend(["--disallowedTools", self.disallowed_tools])
        if spec.system_append:
            argv.extend(["--append-system-prompt", spec.system_append])

        started = time.monotonic()
        try:
            result = self._runner(
                argv, spec.prompt, spec.timeout_seconds, self._child_env(), spec.workspace
            )
        except subprocess.TimeoutExpired:
            return AgentInvocation(
                status="timeout",
                duration_seconds=time.monotonic() - started,
                num_turns=0.0,
                cost_usd=0.0,
                raw_output="",
                detail=f"agent timed out after {spec.timeout_seconds:.0f}s",
            )
        except FileNotFoundError as exc:
            raise ExperimentConfigError(
                f"The claude-cli executor requires the {self.binary!r} binary."
            ) from exc
        duration = time.monotonic() - started

        combined = f"{result.stdout}\n{result.stderr}".lower()
        for marker in _ABORT_MARKERS:
            if marker in combined:
                raise ExperimentAbort(
                    f"Agent auth/credit failure — aborting the experiment: {_tail(result.stdout or result.stderr)}"
                )

        return _parse_agent_json(result, duration)

    def run_batch(self, specs: list[TrialSpec]) -> list[AgentInvocation]:
        return _sequential_run_batch(self, specs)


class HostAgentTrialExecutor:
    """Runs trials through a file handshake with the launching agent session.

    The same contract as the llm-bridge provider, extended from "the session
    answers LLM calls" to "the session runs agent trials": for each trial arm
    the engine writes ``<bridge_dir>/requests/<request-id>.json`` containing
    the complete trial input (prompt, appended system prompt, workspace path,
    timeout) and waits for ``<bridge_dir>/responses/<request-id>.json`` with
    ``{"id", "status", "duration_seconds"?, "num_turns"?, "cost_usd"?,
    "detail"?}``. The host session spawns one fresh subagent per request from
    a fixed template, so no API key or CLI login is involved.

    Whole batches are posted at once so the host can run trials in parallel.
    Answered request files are removed (``requests/`` lists exactly the
    pending trials), a ``stop`` file cancels the experiment, and two
    consecutive fully-unanswered batches abandon it.
    """

    def __init__(
        self,
        bridge_dir: str | Path,
        *,
        response_margin_seconds: float = 300.0,
        poll_seconds: float = DEFAULT_BRIDGE_POLL_SECONDS,
        abandon_after_batches: int = 2,
    ) -> None:
        if not str(bridge_dir).strip():
            raise ExperimentConfigError("The host-agent executor requires a bridge directory.")
        self.bridge_dir = Path(bridge_dir)
        self.requests_dir = self.bridge_dir / "requests"
        self.responses_dir = self.bridge_dir / "responses"
        self.stop_path = self.bridge_dir / BRIDGE_STOP_FILENAME
        self.response_margin_seconds = float(response_margin_seconds)
        self.poll_seconds = max(float(poll_seconds), 0.01)
        self.abandon_after_batches = max(int(abandon_after_batches), 1)
        self._consecutive_unanswered_batches = 0

    def run_batch(self, specs: list[TrialSpec]) -> list[AgentInvocation]:
        if not specs:
            return []
        self._raise_if_stopped(specs=[])
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        for spec in specs:
            _atomic_write_json(
                self.requests_dir / f"{spec.request_id}.json",
                {
                    "id": spec.request_id,
                    "task_id": spec.task_id,
                    "trial": spec.trial,
                    "prompt": spec.prompt,
                    "system_append": spec.system_append,
                    "workspace": spec.workspace,
                    "timeout_seconds": spec.timeout_seconds,
                    "created_at": time.time(),
                },
            )

        pending = {spec.request_id: spec for spec in specs}
        answered: dict[str, AgentInvocation] = {}
        deadline = time.monotonic() + max(spec.timeout_seconds for spec in specs) + (
            self.response_margin_seconds
        )
        while pending and time.monotonic() < deadline:
            self._raise_if_stopped(specs=list(pending.values()))
            for request_id in list(pending):
                parsed = _read_json_object(self.responses_dir / f"{request_id}.json")
                if parsed is None:
                    continue
                (self.requests_dir / f"{request_id}.json").unlink(missing_ok=True)
                answered[request_id] = _invocation_from_bridge_response(parsed)
                del pending[request_id]
            if pending:
                time.sleep(self.poll_seconds)

        for request_id, spec in pending.items():
            (self.requests_dir / f"{request_id}.json").unlink(missing_ok=True)
            answered[request_id] = AgentInvocation(
                status="timeout",
                duration_seconds=spec.timeout_seconds,
                num_turns=0.0,
                cost_usd=0.0,
                raw_output="",
                detail="bridge request was not answered before the deadline",
            )
        if pending and len(pending) == len(specs):
            self._consecutive_unanswered_batches += 1
            if self._consecutive_unanswered_batches >= self.abandon_after_batches:
                raise ExperimentAbort(
                    f"{self._consecutive_unanswered_batches} consecutive trial batches went "
                    "unanswered; the host session appears to have abandoned the bridge."
                )
        elif not pending:
            self._consecutive_unanswered_batches = 0
        return [answered[spec.request_id] for spec in specs]

    def _raise_if_stopped(self, specs: list[TrialSpec]) -> None:
        if not self.stop_path.exists():
            return
        for spec in specs:
            (self.requests_dir / f"{spec.request_id}.json").unlink(missing_ok=True)
        raise ExperimentAbort(f"Experiment bridge stop was requested ({self.stop_path}).")


def _invocation_from_bridge_response(parsed: dict[str, Any]) -> AgentInvocation:
    error = str(parsed.get("error", "") or "").strip()
    if error:
        return AgentInvocation(
            status="error",
            duration_seconds=_float_or_zero(parsed.get("duration_seconds")),
            num_turns=0.0,
            cost_usd=_float_or_zero(parsed.get("cost_usd")),
            raw_output=json.dumps(parsed),
            detail=error[:500],
        )
    status = str(parsed.get("status") or "").strip().lower()
    detail = str(parsed.get("detail") or "")[:500]
    if status not in {"completed", "max-turns", "timeout", "error"}:
        detail = f"unrecognized bridge status {status!r}; {detail}".strip("; ")
        status = "error"
    return AgentInvocation(
        status=status,
        duration_seconds=_float_or_zero(parsed.get("duration_seconds")),
        num_turns=_float_or_zero(parsed.get("num_turns")),
        cost_usd=_float_or_zero(parsed.get("cost_usd")),
        raw_output=json.dumps(parsed),
        detail=detail,
    )


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_agent_json(
    result: subprocess.CompletedProcess[str],
    duration: float,
) -> AgentInvocation:
    raw = result.stdout.strip()
    parsed: dict[str, Any] | None = None
    if raw:
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, dict):
                parsed = candidate
        except json.JSONDecodeError:
            parsed = None

    if parsed is None:
        status = "error"
        detail = _tail(result.stderr) or "agent produced no parseable JSON output"
        return AgentInvocation(
            status=status,
            duration_seconds=duration,
            num_turns=0.0,
            cost_usd=0.0,
            raw_output=raw,
            detail=detail,
        )

    subtype = str(parsed.get("subtype") or "")
    is_error = bool(parsed.get("is_error"))
    if subtype == "error_max_turns":
        status = "max-turns"
    elif is_error or result.returncode != 0:
        status = "error"
    else:
        status = "completed"
    reported_duration = parsed.get("duration_ms")
    return AgentInvocation(
        status=status,
        duration_seconds=(
            float(reported_duration) / 1000.0
            if isinstance(reported_duration, (int, float))
            else duration
        ),
        num_turns=float(parsed.get("num_turns") or 0.0),
        cost_usd=float(parsed.get("total_cost_usd") or 0.0),
        raw_output=raw,
        detail=str(parsed.get("result") or "")[:500] if status == "error" else "",
    )


def _tail(text: str, limit: int = 400) -> str:
    cleaned = (text or "").strip()
    return cleaned[-limit:]


# ---------------------------------------------------------------------------
# Workspace preparation, diffing, grading


def _prepare_workspace(task: AgentTask, arm_dir: Path) -> Path:
    workspace = arm_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(task.workspace_dir(), workspace)
    return workspace


def _workspace_diff(source: Path, workspace: Path) -> str:
    """Human-auditable record of what the agent changed."""

    def _files(root: Path) -> dict[str, Path]:
        return {
            str(item.relative_to(root)): item
            for item in sorted(root.rglob("*"))
            if item.is_file() and "__pycache__" not in item.parts
        }

    before = _files(source)
    after = _files(workspace)
    lines: list[str] = []
    for name in sorted(set(before) | set(after)):
        if name in before and name not in after:
            lines.append(f"deleted: {name}")
            continue
        if name not in before:
            lines.append(f"added: {name}")
            lines.extend(_unified_diff("", _read_for_diff(after[name]), name))
            continue
        old_text = _read_for_diff(before[name])
        new_text = _read_for_diff(after[name])
        if old_text != new_text:
            lines.append(f"modified: {name}")
            lines.extend(_unified_diff(old_text, new_text, name))
    return "\n".join(lines) if lines else "no changes"


def _read_for_diff(path: Path) -> str:
    if path.stat().st_size > _DIFF_MAX_BYTES:
        return f"<file larger than {_DIFF_MAX_BYTES} bytes>"
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "<binary file>"


def _unified_diff(old: str, new: str, name: str) -> list[str]:
    return list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            lineterm="",
        )
    )


def grade_workspace(
    workspace: Path,
    grader_dir: Path,
    *,
    timeout: float = DEFAULT_GRADING_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Copy held-out grader tests into the workspace root and run pytest.

    The grader is copied in only after the agent phase; the task passes iff
    pytest exits 0. Grading uses the engine's interpreter so ``python -m
    pytest`` puts the workspace root on ``sys.path``.
    """

    grader_files = sorted(grader_dir.glob("*.py"))
    if not any(item.name.startswith("test_") for item in grader_files):
        raise ExperimentConfigError(f"No grader test files in {grader_dir}")
    copied_names: list[str] = []
    for item in grader_files:
        shutil.copy2(item, workspace / item.name)
        if item.name.startswith("test_"):
            copied_names.append(item.name)

    env = {key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *copied_names],
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"grader timed out after {timeout:.0f}s"
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    return completed.returncode == 0, output[-2000:]


# ---------------------------------------------------------------------------
# Statistics


def compute_experiment_stats(
    arm_results: list[TrialArmResult],
    *,
    seed: int = DEFAULT_SEED,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
) -> dict[str, float]:
    pairs = _paired_outcomes(arm_results)
    n_pairs = len(pairs)
    if n_pairs == 0:
        return {"n_pairs": 0.0}

    baseline_passes = sum(1 for baseline, _ in pairs.values() if baseline)
    candidate_passes = sum(1 for _, candidate in pairs.values() if candidate)
    candidate_only = sum(1 for baseline, candidate in pairs.values() if candidate and not baseline)
    baseline_only = sum(1 for baseline, candidate in pairs.values() if baseline and not candidate)
    discordant = candidate_only + baseline_only

    baseline_rate = baseline_passes / n_pairs
    candidate_rate = candidate_passes / n_pairs
    delta = candidate_rate - baseline_rate

    p_improvement = _one_sided_binomial(candidate_only, discordant)
    p_regression = _one_sided_binomial(baseline_only, discordant)

    ci_low, ci_high = _bootstrap_delta_ci(
        list(pairs.values()), seed=seed, iterations=bootstrap_iterations
    )

    task_candidate_better, task_baseline_better, task_tied = _task_level_signs(arm_results)
    task_discordant = task_candidate_better + task_baseline_better
    task_sign_p = _one_sided_binomial(task_candidate_better, task_discordant)

    return {
        "n_pairs": float(n_pairs),
        "baseline_pass_rate": round(baseline_rate, 6),
        "candidate_pass_rate": round(candidate_rate, 6),
        "pass_rate_delta": round(delta, 6),
        "candidate_only_wins": float(candidate_only),
        "baseline_only_wins": float(baseline_only),
        "discordant_pairs": float(discordant),
        "mcnemar_p_one_sided": round(p_improvement, 6),
        "mcnemar_p_regression": round(p_regression, 6),
        "delta_ci95_low": round(ci_low, 6),
        "delta_ci95_high": round(ci_high, 6),
        "tasks_candidate_better": float(task_candidate_better),
        "tasks_baseline_better": float(task_baseline_better),
        "tasks_tied": float(task_tied),
        "task_sign_p_one_sided": round(task_sign_p, 6),
    }


def _paired_outcomes(arm_results: list[TrialArmResult]) -> dict[tuple[str, int], tuple[bool, bool]]:
    by_key: dict[tuple[str, int], dict[str, bool]] = {}
    for item in arm_results:
        by_key.setdefault((item.task_id, item.trial), {})[item.arm] = item.passed
    return {
        key: (arms[_ARM_BASELINE], arms[_ARM_CANDIDATE])
        for key, arms in sorted(by_key.items())
        if _ARM_BASELINE in arms and _ARM_CANDIDATE in arms
    }


def _one_sided_binomial(successes: int, trials: int) -> float:
    """P(X >= successes) for X ~ Binomial(trials, 0.5); 1.0 when trials == 0."""

    if trials <= 0:
        return 1.0
    total = sum(math.comb(trials, k) for k in range(successes, trials + 1))
    return min(1.0, total / (2**trials))


def _bootstrap_delta_ci(
    pairs: list[tuple[bool, bool]],
    *,
    seed: int,
    iterations: int,
) -> tuple[float, float]:
    if not pairs or iterations <= 0:
        return 0.0, 0.0
    rng = random.Random(seed + 1)
    deltas: list[float] = []
    count = len(pairs)
    for _ in range(iterations):
        sample = rng.choices(pairs, k=count)
        deltas.append(
            (sum(1 for _, c in sample if c) - sum(1 for b, _ in sample if b)) / count
        )
    deltas.sort()
    low_index = max(0, int(0.025 * iterations) - 1)
    high_index = min(iterations - 1, int(math.ceil(0.975 * iterations)) - 1)
    return deltas[low_index], deltas[high_index]


def _task_level_signs(arm_results: list[TrialArmResult]) -> tuple[int, int, int]:
    per_task: dict[str, dict[str, int]] = {}
    for item in arm_results:
        counts = per_task.setdefault(item.task_id, {_ARM_BASELINE: 0, _ARM_CANDIDATE: 0})
        if item.passed:
            counts[item.arm] += 1
    candidate_better = sum(
        1 for counts in per_task.values() if counts[_ARM_CANDIDATE] > counts[_ARM_BASELINE]
    )
    baseline_better = sum(
        1 for counts in per_task.values() if counts[_ARM_BASELINE] > counts[_ARM_CANDIDATE]
    )
    tied = len(per_task) - candidate_better - baseline_better
    return candidate_better, baseline_better, tied


def decide_verdict(
    stats: dict[str, float],
    *,
    alpha: float = DEFAULT_ALPHA,
    min_discordant_pairs: int = DEFAULT_MIN_DISCORDANT_PAIRS,
) -> str:
    if stats.get("n_pairs", 0.0) <= 0:
        return "inconclusive"
    if stats.get("discordant_pairs", 0.0) < min_discordant_pairs:
        return "inconclusive"
    delta = stats.get("pass_rate_delta", 0.0)
    if stats.get("mcnemar_p_one_sided", 1.0) < alpha and delta > 0:
        return "supported"
    if stats.get("mcnemar_p_regression", 1.0) < alpha and delta < 0:
        return "refuted"
    return "inconclusive"


# ---------------------------------------------------------------------------
# Experiment orchestration


@dataclass(frozen=True)
class TrialArmResult:
    task_id: str
    trial: int
    arm: str
    passed: bool
    agent_status: str
    duration_seconds: float
    num_turns: float
    cost_usd: float
    grader_tail: str = ""
    overtime: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrialArmResult:
        copied = dict(data)
        copied.setdefault("grader_tail", "")
        copied.setdefault("overtime", False)
        return cls(**copied)


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    protocol_hash: str
    status: str  # complete | incomplete
    started_at: str
    finished_at: str
    trial_arms: list[TrialArmResult]
    stats: dict[str, float]
    verdict: str
    total_cost_usd: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["trial_arms"] = [item.to_dict() for item in self.trial_arms]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentResult:
        copied = dict(data)
        copied["trial_arms"] = [
            TrialArmResult.from_dict(item) for item in copied.get("trial_arms", [])
        ]
        copied.setdefault("notes", [])
        return cls(**copied)


TrialExecutor = (
    DeterministicAgentExecutor | ClaudeCliAgentExecutor | HostAgentTrialExecutor
)


def create_executor(
    protocol: ExperimentProtocol,
    *,
    out_dir: str | Path = "",
    env_file: str | Path = ".env",
    script: dict[str, Any] | None = None,
    runner: AgentCommandRunner | None = None,
) -> TrialExecutor:
    if protocol.executor == "deterministic":
        return DeterministicAgentExecutor(script=script)
    if protocol.executor == "host-agent":
        if not str(out_dir).strip():
            raise ExperimentConfigError(
                "The host-agent executor requires the experiment output directory."
            )
        return HostAgentTrialExecutor(Path(out_dir) / "agent-bridge")
    return ClaudeCliAgentExecutor(
        model=protocol.model,
        max_turns=protocol.max_turns,
        allowed_tools=protocol.allowed_tools,
        disallowed_tools=protocol.disallowed_tools,
        agent_auth=protocol.agent_auth,
        env_file=env_file,
        runner=runner,
    )


def run_experiment(
    protocol: ExperimentProtocol,
    tasks: list[AgentTask],
    executor: TrialExecutor,
    out_dir: str | Path,
    *,
    grading_timeout: float = DEFAULT_GRADING_TIMEOUT_SECONDS,
    progress: Callable[[str], None] | None = None,
) -> ExperimentResult:
    tasks_by_id = {task.id: task for task in tasks}
    missing = [task_id for task_id in protocol.task_ids if task_id not in tasks_by_id]
    if missing:
        raise ExperimentConfigError(f"Protocol references unknown tasks: {', '.join(missing)}")

    out_path = Path(out_dir)
    trials_root = out_path / "trials"
    trials_root.mkdir(parents=True, exist_ok=True)
    emit = progress or (lambda _message: None)

    rng = random.Random(protocol.seed)
    schedule: list[tuple[str, int, list[str]]] = []
    for task_id in protocol.task_ids:
        for trial in range(1, protocol.trials_per_task + 1):
            arms = [_ARM_BASELINE, _ARM_CANDIDATE]
            rng.shuffle(arms)
            schedule.append((task_id, trial, arms))

    started_at = datetime.now(timezone.utc).isoformat()
    arm_results: list[TrialArmResult] = []
    notes: list[str] = []
    total_cost = 0.0
    status = "complete"
    chunk_size = max(1, protocol.trial_concurrency)

    try:
        for chunk_start in range(0, len(schedule), chunk_size):
            # The budget is checked between chunks, so the worst overshoot is
            # one chunk of trials; that trade is what buys parallel batches.
            if total_cost > protocol.cost_budget_usd:
                raise _BudgetExceeded()
            chunk = schedule[chunk_start : chunk_start + chunk_size]
            prepared: list[tuple[TrialSpec, AgentTask, Path]] = []
            for task_id, trial, arms in chunk:
                task = tasks_by_id[task_id]
                for arm in arms:
                    prepared.append(_prepare_arm(protocol, task, trial, arm, trials_root))
            invocations = executor.run_batch([spec for spec, _, _ in prepared])
            for (spec, task, arm_dir), invocation in zip(prepared, invocations):
                arm_result = _record_arm(
                    spec, task, arm_dir, invocation, grading_timeout=grading_timeout
                )
                arm_results.append(arm_result)
                total_cost += arm_result.cost_usd
                emit(
                    f"{spec.task_id} trial {spec.trial} {spec.arm}: "
                    f"{'pass' if arm_result.passed else 'fail'} "
                    f"({arm_result.agent_status}, ${total_cost:.2f} spent)"
                )
    except _BudgetExceeded:
        status = "incomplete"
        notes.append(
            f"Stopped: cost budget ${protocol.cost_budget_usd:.2f} exceeded after "
            f"{len(arm_results)} of {len(schedule) * 2} arms."
        )
    except ExperimentAbort as exc:
        status = "incomplete"
        notes.append(f"Aborted: {exc}")

    stats = compute_experiment_stats(arm_results, seed=protocol.seed)
    verdict = (
        decide_verdict(
            stats,
            alpha=protocol.alpha,
            min_discordant_pairs=protocol.min_discordant_pairs,
        )
        if status == "complete"
        else "incomplete"
    )
    result = ExperimentResult(
        experiment_id=protocol.id,
        protocol_hash=protocol.content_hash(),
        status=status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        trial_arms=arm_results,
        stats=stats,
        verdict=verdict,
        total_cost_usd=round(total_cost, 6),
        notes=notes,
    )
    (out_path / "experiment.json").write_text(
        json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    (out_path / "experiment-report.md").write_text(
        render_experiment_report(protocol, result), encoding="utf-8"
    )
    return result


class _BudgetExceeded(Exception):
    pass


def _prepare_arm(
    protocol: ExperimentProtocol,
    task: AgentTask,
    trial: int,
    arm: str,
    trials_root: Path,
) -> tuple[TrialSpec, AgentTask, Path]:
    arm_dir = trials_root / task.id / f"trial-{trial}" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    workspace = _prepare_workspace(task, arm_dir)
    spec = TrialSpec(
        request_id=f"{task.id}-trial{trial}-{arm}",
        task_id=task.id,
        trial=trial,
        arm=arm,
        prompt=task.prompt,
        system_append=protocol.intervention if arm == _ARM_CANDIDATE else "",
        workspace=str(workspace),
        timeout_seconds=min(task.timeout_seconds, protocol.trial_timeout_seconds),
    )
    return spec, task, arm_dir


def _record_arm(
    spec: TrialSpec,
    task: AgentTask,
    arm_dir: Path,
    invocation: AgentInvocation,
    *,
    grading_timeout: float,
) -> TrialArmResult:
    workspace = Path(spec.workspace)
    (arm_dir / "agent-output.json").write_text(
        invocation.raw_output or json.dumps({"status": invocation.status, "detail": invocation.detail}),
        encoding="utf-8",
    )
    (arm_dir / "workspace-diff.txt").write_text(
        _workspace_diff(task.workspace_dir(), workspace), encoding="utf-8"
    )

    # The workspace is graded regardless of agent status: a timed-out or
    # turn-capped agent may still have landed a working change, and that is
    # the outcome that matters.
    passed, grader_tail = grade_workspace(workspace, task.grader_dir(), timeout=grading_timeout)
    (arm_dir / "grader-output.txt").write_text(grader_tail, encoding="utf-8")

    # Overtime rule: an arm that reports more wall time than the trial budget
    # fails even if the graders pass. Executors that cannot hard-kill an agent
    # (the host-agent bridge) still get enforced timeout semantics this way,
    # deterministically and identically for both arms.
    overtime = invocation.duration_seconds > spec.timeout_seconds
    return TrialArmResult(
        task_id=spec.task_id,
        trial=spec.trial,
        arm=spec.arm,
        passed=passed and not overtime,
        agent_status=invocation.status,
        duration_seconds=round(invocation.duration_seconds, 3),
        num_turns=invocation.num_turns,
        cost_usd=round(invocation.cost_usd, 6),
        grader_tail=grader_tail[-400:],
        overtime=overtime,
    )


# ---------------------------------------------------------------------------
# Benchmark conversion and report rendering


def benchmark_result_from_experiment(
    protocol: ExperimentProtocol,
    result: ExperimentResult,
) -> BenchmarkResult:
    baseline_arms = [item for item in result.trial_arms if item.arm == _ARM_BASELINE]
    candidate_arms = [item for item in result.trial_arms if item.arm == _ARM_CANDIDATE]
    stats = result.stats
    baseline_metrics = {
        "pass_rate": stats.get("baseline_pass_rate", 0.0),
        "regression_count": 0.0,
        "tool_calls": _mean(item.num_turns for item in baseline_arms),
        "wall_time": _mean(item.duration_seconds for item in baseline_arms),
        "cost": round(sum(item.cost_usd for item in baseline_arms), 6),
    }
    candidate_metrics = {
        "pass_rate": stats.get("candidate_pass_rate", 0.0),
        "regression_count": stats.get("baseline_only_wins", 0.0),
        "tool_calls": _mean(item.num_turns for item in candidate_arms),
        "wall_time": _mean(item.duration_seconds for item in candidate_arms),
        "cost": round(sum(item.cost_usd for item in candidate_arms), 6),
    }
    deltas = {
        metric: round(candidate_metrics[metric] - baseline_metrics[metric], 6)
        for metric in baseline_metrics
    }
    notes = [
        f"experiment {result.experiment_id} ({result.status}); protocol sha256 {result.protocol_hash[:16]}",
        f"verdict {result.verdict}: delta {stats.get('pass_rate_delta', 0.0):+.3f} "
        f"[{stats.get('delta_ci95_low', 0.0):+.3f}, {stats.get('delta_ci95_high', 0.0):+.3f}] CI95, "
        f"one-sided McNemar p={stats.get('mcnemar_p_one_sided', 1.0):.4f} over "
        f"{int(stats.get('discordant_pairs', 0))} discordant of {int(stats.get('n_pairs', 0))} pairs",
        *result.notes,
    ]
    return BenchmarkResult(
        id=stable_id("bench-measured", f"{protocol.id}:{result.protocol_hash}"),
        name=f"Measured: {protocol.hypothesis_title}",
        source=f"experiment:{protocol.id}",
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        deltas=deltas,
        success=result.verdict == "supported",
        notes=notes,
        provenance=MEASURED_PROVENANCE,
        hypothesis_id=protocol.hypothesis_id,
        verdict=result.verdict,
        stats=dict(stats),
    )


def _mean(values: Any) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 6)


def render_experiment_report(protocol: ExperimentProtocol, result: ExperimentResult) -> str:
    stats = result.stats
    per_task: dict[str, dict[str, list[bool]]] = {}
    for item in result.trial_arms:
        per_task.setdefault(item.task_id, {}).setdefault(item.arm, []).append(item.passed)

    lines = [
        f"# Experiment Report: {protocol.hypothesis_title}",
        "",
        f"- Experiment: `{protocol.id}` (protocol sha256 `{result.protocol_hash}`)",
        f"- Hypothesis: `{protocol.hypothesis_id}` — {protocol.hypothesis_claim}",
        f"- Executor: {protocol.executor} (model `{protocol.model or 'n/a'}`, "
        f"max {protocol.max_turns} turns, auth {protocol.agent_auth})",
        f"- Tasks: {len(protocol.task_ids)} × {protocol.trials_per_task} paired trials, seed {protocol.seed}",
        f"- Status: **{result.status}**, verdict: **{result.verdict}**",
        f"- Total measured cost: ${result.total_cost_usd:.2f} (budget ${protocol.cost_budget_usd:.2f})",
        "",
        "## Intervention (candidate arm `--append-system-prompt`)",
        "",
        "```",
        protocol.intervention,
        "```",
        "",
        f"Baseline: {protocol.baseline_description}",
        "",
        "## Outcomes By Task",
        "",
        "| Task | Baseline passes | Candidate passes |",
        "| --- | --- | --- |",
    ]
    for task_id in protocol.task_ids:
        arms = per_task.get(task_id, {})
        baseline = arms.get(_ARM_BASELINE, [])
        candidate = arms.get(_ARM_CANDIDATE, [])
        lines.append(
            f"| {task_id} | {sum(baseline)}/{len(baseline)} | {sum(candidate)}/{len(candidate)} |"
        )
    lines.extend(
        [
            "",
            "## Statistics",
            "",
            f"- Pairs: {int(stats.get('n_pairs', 0))} "
            f"(baseline pass rate {stats.get('baseline_pass_rate', 0.0):.3f}, "
            f"candidate {stats.get('candidate_pass_rate', 0.0):.3f})",
            f"- Pass-rate delta: {stats.get('pass_rate_delta', 0.0):+.3f} "
            f"(bootstrap CI95 [{stats.get('delta_ci95_low', 0.0):+.3f}, {stats.get('delta_ci95_high', 0.0):+.3f}])",
            f"- Discordant pairs: {int(stats.get('discordant_pairs', 0))} "
            f"(candidate-only wins {int(stats.get('candidate_only_wins', 0))}, "
            f"baseline-only wins {int(stats.get('baseline_only_wins', 0))})",
            f"- Primary (pre-registered): one-sided exact McNemar p = {stats.get('mcnemar_p_one_sided', 1.0):.4f} "
            f"at alpha {protocol.alpha} with minimum {protocol.min_discordant_pairs} discordant pairs",
            f"- Robustness: task-level sign test p = {stats.get('task_sign_p_one_sided', 1.0):.4f} "
            f"({int(stats.get('tasks_candidate_better', 0))} tasks better, "
            f"{int(stats.get('tasks_baseline_better', 0))} worse, "
            f"{int(stats.get('tasks_tied', 0))} tied)",
            "",
            "## Caveats",
            "",
            "- Pairs within a task share a task effect; the pair-level McNemar test is "
            "mildly anticonservative under clustering. The task-level sign test is the "
            "robustness check.",
            "- Execution policy is trusted_local: trials ran as local subprocesses in "
            "temporary workspace copies with no sandbox-isolation claim.",
            "- Results are specific to the task suite, model, and turn/timeout limits "
            "registered in the protocol; they do not establish generality beyond them.",
        ]
    )
    if result.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in result.notes)
    lines.append("")
    return "\n".join(lines)
