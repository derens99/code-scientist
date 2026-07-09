# Paper Alignment Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the paper's two missing evaluation methods — Elo-vs-correctness concordance (§4.1) and temporal Elo trajectory (§4.2 Fig 4) — plus per-task drain buffers so review concurrency delivers real parallelism (spec: `docs/superpowers/specs/2026-07-09-paper-alignment-wave2-design.md`).

**Architecture:** New `concordance.py` module for the §4.1 method; two additive RunState collections (`elo_trajectory`, `elo_concordance`) with tolerant `from_dict` defaults; thread-local storage for the two shared drain buffers so the Wave 1 review `state_lock` can shrink to shared-list mutations only. No breaking schema changes.

**Tech Stack:** Python 3.12 + dataclasses, pytest via `uv run pytest`, stdlib only.

**Conventions for every task:** always `uv run`, never bare python/pip; TDD — write the failing test, run it, watch it fail for the right reason, then implement; old `state.json` files must keep loading (setdefault pattern in `from_dict`); commit on `feature/paper-alignment-wave2`; plan line references may drift — locate by name.

---

### Task 1: EloTrajectoryPoint model + RunState field

**Files:**
- Modify: `src/code_scientist/models.py` (new dataclass near `ScalingCurvePoint` ~line 620; `RunState` field + `to_dict`/`from_dict`)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests.**

```python
def test_elo_trajectory_point_round_trips():
    point = EloTrajectoryPoint(
        cycle=1, match_index=0, match_id="match-1",
        best_elo=1250.0, top_avg_elo=1215.5, active_count=6,
    )
    restored = EloTrajectoryPoint.from_dict(point.to_dict())
    assert restored == point


def test_run_state_defaults_elo_trajectory_for_old_state():
    state = RunState(goal=ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents"))
    data = state.to_dict()
    data.pop("elo_trajectory", None)  # simulate old state.json
    restored = RunState.from_dict(data)
    assert restored.elo_trajectory == []
```

Mirror the neighboring round-trip tests' style in `tests/test_models.py` (check how they build `RunState` and which import list to extend).

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_models.py -q -k elo_trajectory` — expected: FAIL (`ImportError`/`AttributeError`).

- [ ] **Step 3: Implement.**

```python
@dataclass(frozen=True)
class EloTrajectoryPoint:
    cycle: int
    match_index: int
    match_id: str
    best_elo: float
    top_avg_elo: float
    active_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EloTrajectoryPoint:
        return cls(**data)
```

Add `elo_trajectory: list[EloTrajectoryPoint] = field(default_factory=list)` to `RunState` (place after `scaling_curve`), serialize it in `RunState.to_dict`, and in `RunState.from_dict` follow the existing pattern for list fields (find how `scaling_curve` is reconstructed and mirror it, with a `data.get("elo_trajectory", [])` tolerant default).

- [ ] **Step 4: Run.** `uv run pytest tests/test_models.py -q` — expected: PASS.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: add elo trajectory point model and run-state field"`

---

### Task 2: Record the trajectory per match + report it

**Files:**
- Modify: `src/code_scientist/supervisor.py` (`run_research_cycle`: run-scoped list, `execute_ranking` loop ~line 695-737, `current_state()` closure, resume path via `load_state`)
- Modify: `src/code_scientist/reporting.py` (new "Elo Trajectory" section)
- Test: `tests/test_supervisor.py`, `tests/test_reporting.py`

- [ ] **Step 1: Write the failing supervisor test.**

```python
def test_run_records_elo_trajectory_per_match(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=2, max_hypotheses=6, max_matches=4, out_dir=tmp_path / "run",
    )
    assert state.matches, "expected matches"
    assert len(state.elo_trajectory) == len(state.matches)
    indices = [point.match_index for point in state.elo_trajectory]
    assert indices == list(range(len(state.elo_trajectory))), "global monotonic match_index"
    for point, match in zip(state.elo_trajectory, state.matches):
        assert point.match_id == match.id
        assert point.best_elo >= point.top_avg_elo > 0
        assert point.active_count > 0
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`elo_trajectory` empty).

- [ ] **Step 3: Implement recording.** In `run_research_cycle`: create `elo_trajectory: list[EloTrajectoryPoint] = list(loaded_state.elo_trajectory) if resuming else []` alongside `matches` (mirror exactly how `matches` is initialized/resumed). In `execute_ranking`, right after `matches.append(match)`:

```python
active = _active_hypotheses(hypotheses)
ranked_elos = sorted((item.elo for item in active), reverse=True)
top_slice = ranked_elos[: min(10, len(ranked_elos))]
elo_trajectory.append(
    EloTrajectoryPoint(
        cycle=cycle,
        match_index=len(elo_trajectory),
        match_id=match.id,
        best_elo=round(ranked_elos[0], 3) if ranked_elos else 0.0,
        top_avg_elo=round(sum(top_slice) / len(top_slice), 3) if top_slice else 0.0,
        active_count=len(active),
    )
)
```

Thread `elo_trajectory=elo_trajectory` into the `current_state()`/`RunState(...)` construction (find every `RunState(` construction in `run_research_cycle` and its persistence closure).

- [ ] **Step 4: Run.** `uv run pytest tests/test_supervisor.py -q -k elo_trajectory` — expected: PASS.

- [ ] **Step 5: Write the failing reporting test.**

```python
def test_render_report_includes_elo_trajectory_section(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=2, max_hypotheses=6, max_matches=4, out_dir=tmp_path / "run",
    )
    report = render_report(state)
    assert "## Elo Trajectory" in report
    assert f"Points recorded: {len(state.elo_trajectory)}" in report
```

- [ ] **Step 6: Implement the section.** In `reporting.py`, following the style of neighboring optional sections (render only when `state.elo_trajectory` is non-empty): heading `## Elo Trajectory`, lines for `Points recorded: N`, first/last/max `best_elo`, first/last `top_avg_elo`. When empty, omit the section entirely (match how other empty-optional sections behave — read one first).

- [ ] **Step 7: Run both suites.** `uv run pytest tests/test_supervisor.py tests/test_reporting.py -q` — expected: PASS.
- [ ] **Step 8: Commit.** `git add -A && git commit -m "feat: record per-match elo trajectory and render it in reports"`

---

### Task 3: EloConcordanceResult model + RunState field

**Files:**
- Modify: `src/code_scientist/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests.**

```python
def test_elo_concordance_result_round_trips():
    result = EloConcordanceResult(
        id="conc-1", benchmark_name="objective-demo", question="Which fix passes the test?",
        graded_count=4, ungraded_count=1, overall_accuracy=0.75,
        top_hypothesis_id="hyp-1", top_hypothesis_correct=True,
        concordance_index=0.833,
        buckets=[{"bucket": 0.0, "elo_max": 1300.0, "elo_min": 1250.0, "count": 2.0, "accuracy": 1.0}],
        notes=["graded via answer extraction"],
    )
    assert EloConcordanceResult.from_dict(result.to_dict()) == result


def test_run_state_defaults_elo_concordance_for_old_state():
    state = RunState(goal=ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents"))
    data = state.to_dict()
    data.pop("elo_concordance", None)
    assert RunState.from_dict(data).elo_concordance == []
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (ImportError).

- [ ] **Step 3: Implement.**

```python
@dataclass(frozen=True)
class EloConcordanceResult:
    id: str
    benchmark_name: str
    question: str
    graded_count: int
    ungraded_count: int
    overall_accuracy: float
    top_hypothesis_id: str
    top_hypothesis_correct: bool
    concordance_index: float
    buckets: list[dict[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EloConcordanceResult:
        copied = dict(data)
        copied.setdefault("buckets", [])
        copied.setdefault("notes", [])
        return cls(**copied)
```

Add `elo_concordance: list[EloConcordanceResult] = field(default_factory=list)` to `RunState` with to_dict/from_dict handling as in Task 1.

- [ ] **Step 4: Run.** `uv run pytest tests/test_models.py -q` — expected: PASS.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: add elo concordance result model and run-state field"`

---

### Task 4: Objective benchmark loading + hypothesis grading

**Files:**
- Create: `src/code_scientist/concordance.py`
- Test: `tests/test_concordance.py` (new file)

- [ ] **Step 1: Write the failing tests.**

```python
import json

from code_scientist.concordance import grade_hypotheses, load_objective_benchmark
from code_scientist.models import ResearchGoal
from code_scientist.agents import GenerationAgent
from dataclasses import replace


def _benchmark_file(tmp_path, **overrides):
    payload = {
        "name": "objective-demo",
        "question": "Which retry strategy fixes the flaky integration test?",
        "answer": "backoff",
        **overrides,
    }
    path = tmp_path / "objective.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_objective_benchmark_validates_required_fields(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    assert benchmark.name == "objective-demo"
    assert benchmark.answer == "backoff"


def test_grade_hypotheses_extracts_declared_answers(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=3)
    correct = replace(base[0], rationale=base[0].rationale + " Answer: backoff")
    wrong = replace(base[1], rationale=base[1].rationale + " Answer: retry-once")
    ungraded = base[2]  # declares no answer

    grades = grade_hypotheses(benchmark, [correct, wrong, ungraded])

    assert grades[correct.id] is True
    assert grades[wrong.id] is False
    assert ungraded.id not in grades


def test_grade_hypotheses_explicit_grades_override_extraction(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=2)
    hypothesis = replace(base[0], rationale=base[0].rationale + " Answer: backoff")

    grades = grade_hypotheses(benchmark, [hypothesis, base[1]], grades={hypothesis.id: False, base[1].id: True})

    assert grades[hypothesis.id] is False  # explicit grade wins
    assert grades[base[1].id] is True     # explicit grade covers unextractable hypothesis
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_concordance.py -q` — expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement.**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from code_scientist.models import Hypothesis

_DEFAULT_ANSWER_PATTERN = r"answer\s*[:=]\s*([A-Za-z0-9_.-]+)"


@dataclass(frozen=True)
class ObjectiveBenchmark:
    name: str
    question: str
    answer: str
    answer_pattern: str = _DEFAULT_ANSWER_PATTERN


def load_objective_benchmark(path: str | Path) -> ObjectiveBenchmark:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for field_name in ("name", "question", "answer"):
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Objective benchmark requires non-empty string field '{field_name}'.")
    return ObjectiveBenchmark(
        name=data["name"].strip(),
        question=data["question"].strip(),
        answer=data["answer"].strip(),
        answer_pattern=data.get("answer_pattern") or _DEFAULT_ANSWER_PATTERN,
    )


def grade_hypotheses(
    benchmark: ObjectiveBenchmark,
    hypotheses: list[Hypothesis],
    grades: dict[str, bool] | None = None,
) -> dict[str, bool]:
    pattern = re.compile(benchmark.answer_pattern, re.IGNORECASE)
    graded: dict[str, bool] = {}
    for hypothesis in hypotheses:
        text = f"{hypothesis.title} {hypothesis.claim} {hypothesis.rationale}"
        match = pattern.search(text)
        if match:
            graded[hypothesis.id] = match.group(1).strip().lower() == benchmark.answer.lower()
    for hypothesis_id, verdict in (grades or {}).items():
        graded[hypothesis_id] = bool(verdict)
    return graded
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_concordance.py -q` — expected: PASS.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: objective benchmark loading and ground-truth hypothesis grading"`

---

### Task 5: Concordance analysis (buckets, top-1, concordance index)

**Files:**
- Modify: `src/code_scientist/concordance.py`
- Test: `tests/test_concordance.py`

- [ ] **Step 1: Write the failing tests.** Build hypotheses with controlled Elo via `dataclasses.replace` (Hypothesis has an `elo` field):

```python
def test_compute_elo_concordance_buckets_and_top1(tmp_path):
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=4)
    hyps = [
        replace(base[0], elo=1400.0),  # correct
        replace(base[1], elo=1300.0),  # correct
        replace(base[2], elo=1200.0),  # wrong
        replace(base[3], elo=1100.0),  # wrong
    ]
    correctness = {hyps[0].id: True, hyps[1].id: True, hyps[2].id: False, hyps[3].id: False}

    result = compute_elo_concordance("objective-demo", "Which fix?", hyps, correctness)

    assert result.graded_count == 4
    assert result.overall_accuracy == 0.5
    assert result.top_hypothesis_id == hyps[0].id
    assert result.top_hypothesis_correct is True
    # every (correct, incorrect) pair has the correct one at higher Elo
    assert result.concordance_index == 1.0
    assert len(result.buckets) == 4
    assert result.buckets[0]["accuracy"] == 1.0 and result.buckets[-1]["accuracy"] == 0.0


def test_compute_elo_concordance_handles_ties_and_single_class():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=2)
    hyps = [replace(base[0], elo=1200.0), replace(base[1], elo=1200.0)]

    tie_result = compute_elo_concordance("b", "q", hyps, {hyps[0].id: True, hyps[1].id: False})
    assert tie_result.concordance_index == 0.5  # equal Elo counts half

    single_class = compute_elo_concordance("b", "q", hyps, {hyps[0].id: True, hyps[1].id: True})
    assert single_class.concordance_index == 0.5  # no (correct, incorrect) pairs
    assert single_class.overall_accuracy == 1.0


def test_compute_elo_concordance_excludes_inactive_and_counts_ungraded():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=3)
    quarantined = replace(base[0], elo=1500.0, status="quarantined")
    graded = replace(base[1], elo=1300.0)
    ungraded = replace(base[2], elo=1200.0)

    result = compute_elo_concordance(
        "b", "q", [quarantined, graded, ungraded],
        {quarantined.id: True, graded.id: True},
    )

    assert result.graded_count == 1          # quarantined excluded even though graded
    assert result.ungraded_count == 1        # active but ungraded
    assert result.top_hypothesis_id == graded.id
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`ImportError: compute_elo_concordance`).

- [ ] **Step 3: Implement.**

```python
from code_scientist.models import EloConcordanceResult, stable_id

_INACTIVE_STATUSES = {"merged_duplicate", "quarantined"}


def compute_elo_concordance(
    benchmark_name: str,
    question: str,
    hypotheses: list[Hypothesis],
    correctness: dict[str, bool],
) -> EloConcordanceResult:
    active = [item for item in hypotheses if item.status not in _INACTIVE_STATUSES]
    graded = sorted(
        (item for item in active if item.id in correctness),
        key=lambda item: item.elo,
        reverse=True,
    )
    ungraded_count = len(active) - len(graded)
    accuracy = (
        round(sum(1 for item in graded if correctness[item.id]) / len(graded), 3) if graded else 0.0
    )
    top = graded[0] if graded else None

    correct_elos = [item.elo for item in graded if correctness[item.id]]
    incorrect_elos = [item.elo for item in graded if not correctness[item.id]]
    if correct_elos and incorrect_elos:
        score = sum(
            1.0 if good > bad else 0.5 if good == bad else 0.0
            for good in correct_elos
            for bad in incorrect_elos
        )
        concordance_index = round(score / (len(correct_elos) * len(incorrect_elos)), 3)
    else:
        concordance_index = 0.5

    buckets: list[dict[str, float]] = []
    bucket_count = min(4, len(graded))
    if bucket_count:
        size, remainder = divmod(len(graded), bucket_count)
        start = 0
        for index in range(bucket_count):
            end = start + size + (1 if index < remainder else 0)
            members = graded[start:end]
            buckets.append(
                {
                    "bucket": float(index),
                    "elo_max": round(members[0].elo, 3),
                    "elo_min": round(members[-1].elo, 3),
                    "count": float(len(members)),
                    "accuracy": round(
                        sum(1 for item in members if correctness[item.id]) / len(members), 3
                    ),
                }
            )
            start = end

    identity = f"{benchmark_name}:{question}:{len(graded)}:{accuracy}:{concordance_index}"
    return EloConcordanceResult(
        id=stable_id("conc", identity),
        benchmark_name=benchmark_name,
        question=question,
        graded_count=len(graded),
        ungraded_count=ungraded_count,
        overall_accuracy=accuracy,
        top_hypothesis_id=top.id if top else "",
        top_hypothesis_correct=bool(top and correctness[top.id]),
        concordance_index=concordance_index,
        buckets=buckets,
        notes=[],
    )
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_concordance.py -q` — expected: PASS.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: elo-vs-correctness concordance analysis with buckets and top-1"`

---

### Task 6: `elo-concordance` CLI + report section + study coverage

**Files:**
- Modify: `src/code_scientist/cli.py` (new subcommand parser + branch, following the `agent-packets` pattern)
- Modify: `src/code_scientist/reporting.py` ("Elo Concordance" section)
- Modify: `src/code_scientist/evaluation.py` (`audit_capability_study_coverage` gains `elo_concordance_count` and `elo_trajectory_point_count`)
- Test: `tests/test_cli.py`, `tests/test_reporting.py`, the evaluation-coverage test file (`grep -rln "audit_capability_study_coverage" tests/`)

- [ ] **Step 1: Write the failing CLI test.**

```python
def test_cli_elo_concordance_grades_state_and_saves_result(tmp_path):
    out_dir = tmp_path / "run"
    from code_scientist.supervisor import run_research_cycle, load_state
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1, max_hypotheses=3, max_matches=1, out_dir=out_dir,
    )
    benchmark_path = tmp_path / "objective.json"
    benchmark_path.write_text(json.dumps({
        "name": "objective-demo",
        "question": "Which retry strategy fixes the flaky test?",
        "answer": "backoff",
    }), encoding="utf-8")
    grades_path = tmp_path / "grades.json"
    grades_path.write_text(json.dumps({state.hypotheses[0].id: True, state.hypotheses[1].id: False}), encoding="utf-8")

    exit_code = main([
        "elo-concordance", str(out_dir / "state.json"),
        "--objective-benchmark", str(benchmark_path),
        "--grades", str(grades_path),
    ])

    assert exit_code == 0
    saved = load_state(out_dir / "state.json")
    assert saved.elo_concordance, "result appended to state"
    assert saved.elo_concordance[-1].benchmark_name == "objective-demo"
    assert saved.elo_concordance[-1].graded_count == 2
```

Check how existing CLI tests import `main` and how state is re-saved elsewhere (grep for `save_state` or how `evaluation-return`/`source-attachment` branches persist a modified state — reuse the same helper).

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`invalid choice: 'elo-concordance'`).

- [ ] **Step 3: Implement the subcommand.** Parser:

```python
elo_concordance_parser = subparsers.add_parser(
    "elo-concordance",
    help="Grade hypotheses against an objective benchmark and record Elo-vs-correctness concordance.",
)
elo_concordance_parser.add_argument("state_json")
elo_concordance_parser.add_argument("--objective-benchmark", required=True)
elo_concordance_parser.add_argument("--grades", default="")
```

Branch: load state; `benchmark = load_objective_benchmark(args.objective_benchmark)`; optional grades JSON (`json.loads(Path(args.grades).read_text())` mapping id→bool) when provided; `correctness = grade_hypotheses(benchmark, state.hypotheses, grades=grades)`; `result = compute_elo_concordance(benchmark.name, benchmark.question, state.hypotheses, correctness)`; append via `dataclasses.replace(state, elo_concordance=[*state.elo_concordance, result])`; save with the same persistence helper other state-mutating CLI branches use; print `overall_accuracy`, `top_hypothesis_correct`, `concordance_index`; return 0.

- [ ] **Step 4: Reporting + coverage tests then implementation.** Failing tests first:

```python
def test_render_report_includes_elo_concordance_section():
    # build a minimal RunState with one EloConcordanceResult like neighboring reporting fixtures
    ...
    report = render_report(state)
    assert "## Elo Concordance" in report
    assert "Concordance index" in report
```

and extend the existing coverage-audit test to assert the two new count keys appear (read the current test for exact shape). Implement: reporting section (benchmark name, graded/ungraded, overall accuracy, top-1 verdict, concordance index, per-bucket lines) rendered only when `state.elo_concordance` non-empty; `audit_capability_study_coverage` adds `elo_concordance_count` and `elo_trajectory_point_count` following the exact pattern of its existing count entries.

- [ ] **Step 5: Run.** `uv run pytest tests/test_cli.py tests/test_reporting.py tests/test_evaluation*.py -q` (adjust to the real evaluation test filename) — expected: PASS. Then full `uv run pytest -q`.
- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: elo-concordance CLI, report section, and study coverage tracking"`

---

### Task 7: Thread-local drain buffers

**Files:**
- Modify: `src/code_scientist/evidence.py` (`EvidenceStore._retrieval_memory` → thread-local)
- Modify: `src/code_scientist/agents.py` (`_LLMTraceMixin._llm_interactions` → thread-local)
- Test: `tests/test_evidence.py` (or wherever EvidenceStore tests live — `grep -rln "consume_retrieval_memory" tests/`), `tests/test_agents.py`

- [ ] **Step 1: Write the failing tests.**

```python
def test_retrieval_memory_is_isolated_per_thread(...):
    # Build an EvidenceStore with a couple of Evidence records (reuse existing test fixtures).
    # On the main thread: store.retrieve("query one") then in a worker thread (threading.Thread):
    # store.retrieve("query two") followed by records = store.consume_retrieval_memory(cycle=1, agent="reflection", task_id="task-w", reason="r")
    # Join, then main thread: main_records = store.consume_retrieval_memory(cycle=1, agent="reflection", task_id="task-m", reason="r")
    # Assert: worker records reference only "query two" and task_id "task-w";
    # main records reference only "query one" and task_id "task-m"; no record lost or duplicated.


def test_llm_interactions_are_isolated_per_thread():
    # Use an agent with a FakeLLM (existing pattern): trigger one LLM call on the main thread and one
    # inside a worker thread, drain via consume_llm_interactions() inside each thread,
    # assert each drain returns exactly its own interaction (match on prompt text).
```

Write these as real tests using the file's existing fixtures — the comments above state the required behavior; the assertions must check record contents, not just counts.

- [ ] **Step 2: Run to verify failure.** Expected: FAIL — with the current single shared list, the worker's consume drains the main thread's records too (record contents/task_id assertions break).

- [ ] **Step 3: Implement.** In `EvidenceStore.__init__`: replace the `_retrieval_memory` list with `self._retrieval_local = threading.local()` and a private accessor:

```python
def _retrieval_buffer(self) -> list[...]:
    buffer = getattr(self._retrieval_local, "records", None)
    if buffer is None:
        buffer = []
        self._retrieval_local.records = buffer
    return buffer
```

Every append site uses `self._retrieval_buffer().append(...)`; `consume_retrieval_memory` drains only `self._retrieval_buffer()` (copy, clear, enrich exactly as today). Mirror the identical pattern in `_LLMTraceMixin` for `_llm_interactions`. Preserve public method signatures exactly. Check for any direct external accesses to the old attributes (`grep -rn "_retrieval_memory\|_llm_interactions" src tests`) and update them.

- [ ] **Step 4: Run.** `uv run pytest -q` — expected: all PASS (single-threaded flows are unaffected: one thread → one buffer).
- [ ] **Step 5: Commit.** `git add -A && git commit -m "refactor: thread-local drain buffers for retrieval memory and llm traces"`

---

### Task 8: Narrow the review lock — real parallelism

**Files:**
- Modify: `src/code_scientist/supervisor.py` (`make_execute_review` closure, `_review_for_plan` signature)
- Test: `tests/test_supervisor.py` (replace `test_review_stage_state_lock_serializes_concurrent_review_execution`)

- [ ] **Step 1: Rewrite the serialization test into a parallelism test (failing first).** Replace `test_review_stage_state_lock_serializes_concurrent_review_execution` with:

```python
def test_review_stage_overlaps_concurrent_review_work(tmp_path, monkeypatch):
    # Same instrumentation pattern as the old test: wrap supervisor_module._review_for_plan,
    # count concurrent entries with a private lock, sleep 0.05 inside, record max_observed.
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1, max_hypotheses=4, max_matches=2, out_dir=tmp_path / "run",
        review_concurrency=3,
    )
    assert max_observed >= 2, "review work must overlap once the lock is narrowed"
    review_ids = [review.id for review in state.reviews]
    assert len(review_ids) == len(set(review_ids)), "no duplicated reviews under concurrency"
    review_tasks = [t for t in state.task_queue if t.kind == "review"]
    assert review_tasks and all(t.status == "completed" for t in review_tasks)
```

Also add an attribution test: run with `review_concurrency=3` and evidence grounding (pass `evidence_paths` like existing grounded tests do), then assert every `state.retrieval_memory` record's `task_id` matches a review task that actually reviewed the hypothesis the retrieval was for (at minimum: all task_ids are real task ids from `state.task_queue`, and no record has an empty task_id).

- [ ] **Step 2: Run to verify failure.** The overlap test FAILS on current code (`max_observed == 1` — the wide lock forbids overlap).

- [ ] **Step 3: Implement.** In `make_execute_review`: take the `prior_reviews` snapshot under `state_lock`, run `_review_for_plan(...)` OUTSIDE the lock, and re-acquire `state_lock` only for the shared mutations (appends to `reviews`, `reviewed`, `hypotheses` bookkeeping). `_review_for_plan` internally appends to `agent_traces` and extends `retrieval_memory` — give it a keyword-only `state_lock: threading.Lock | None = None` and wrap only those append/extend statements in `with state_lock:` when provided (a `contextlib.nullcontext()` fallback keeps the unlocked call sites unchanged). The LLM call and `consume_*` drains (now thread-local, Task 7) stay unlocked. All other `_review_for_plan` call sites pass no lock (they run at concurrency 1).

- [ ] **Step 4: Run repeatedly.** `uv run pytest tests/test_supervisor.py -q` then the overlap + attribution tests 5x each for flake, then full `uv run pytest -q`. Expected: all PASS, deterministic default runs untouched (`review_concurrency=1` keeps one thread).
- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: narrow review lock so bounded concurrency overlaps llm and retrieval work"`

---

### Task 9: Full verification + audit annotations

**Files:**
- Modify: `docs/paper-alignment-audit-2026-07-04.md`

- [ ] **Step 1:** `uv run pytest -q` — all PASS (≥360 expected).
- [ ] **Step 2:** `cd web && npm test && npm run typecheck` — PASS (new state fields are additive JSON).
- [ ] **Step 3: Smoke.** `uv run code-scientist run "Find testable ideas that could improve LLM coding agents" --cycles 2 --max-hypotheses 6 --max-matches 4 --out runs/wave2-smoke` then verify `state.json` has a populated `elo_trajectory` (one point per match, monotonic `match_index`); then exercise the concordance CLI end-to-end against that state with a synthetic objective fixture + grades file; verify the report renders both new sections. `rm -rf runs/wave2-smoke` afterwards (runs/ is gitignored; never commit artifacts).
- [ ] **Step 4:** Annotate the audit doc's Evaluation-Method Gaps: mark the Elo-vs-correctness concordance and temporal-Elo-trajectory bullets "resolved in Wave 2 (`feature/paper-alignment-wave2`)", and update the coverage-audit bullet (it now tracks both). Leave LLM-as-judge and frontier-baseline bullets un-annotated (not in this wave). Also update the Wave 1 concurrency annotation if it mentions serialized review execution — reviews now genuinely parallelize.
- [ ] **Step 5: Commit.** `git add -A && git commit -m "docs: mark wave 2 evaluation methods resolved in alignment audit"`
