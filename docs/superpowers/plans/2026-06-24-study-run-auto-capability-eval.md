# Study-Run Auto Capability Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `code-scientist study-run` produce an explicit deterministic baseline comparison from produced hypotheses when a manifest opts into proxy capability evaluation.

**Architecture:** Add a deterministic proxy capability evaluator that scores the current run's ranked hypotheses from inspectable run signals such as Elo, accepted status, evidence refs, test metrics, and benchmark-like wording. Add opt-in manifest fields (`auto_capability_eval`, `baseline_name`, `baseline_score`) and append the resulting `CapabilityEvaluation` before scaling points are derived. Keep human and benchmark score counts at zero so the coverage audit still requires real external evidence for paper-level completion.

**Tech Stack:** Python dataclasses, JSON manifest parsing, `CapabilityEvaluation`, pytest, CLI tests.

---

### Task 1: Proxy Capability Evaluation

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `src/code_scientist/evaluation.py`

- [x] **Step 1: Write the failing evaluation test**

Add `test_auto_capability_evaluation_scores_ranked_hypotheses_without_external_counts`:

```python
def test_auto_capability_evaluation_scores_ranked_hypotheses_without_external_counts():
    goal = ResearchGoal.from_objective("Improve LLM coding agents with retrieval")
    low = Hypothesis(
        id="hyp-low",
        title="Thin idea",
        claim="Try another prompt.",
        rationale="No retrieved evidence yet.",
        assumptions=["Prompt wording matters."],
        evidence_refs=[],
        test_plan=TestPlan(
            experiment="Manual smoke test",
            metrics=[],
            success_condition="Looks better",
        ),
        risks=["Too generic."],
        origin="generation",
        elo=1180,
        status="candidate",
    )
    high = Hypothesis(
        id="hyp-high",
        title="Benchmark-grounded verifier",
        claim="Use retrieved benchmark traces and regression counts before accepting patches.",
        rationale="Evidence-backed verification should improve pass_rate without increasing regression_count.",
        assumptions=["Benchmark traces are representative."],
        evidence_refs=["ev-benchmark"],
        test_plan=TestPlan(
            experiment="Run repair benchmark with and without verification.",
            metrics=["pass_rate", "regression_count"],
            success_condition="pass_rate improves and regression_count does not increase",
        ),
        risks=["May overfit to benchmark traces."],
        origin="generation",
        elo=1460,
        status="accepted",
    )

    evaluation = evaluate_capability_proxy(
        goal=goal,
        hypotheses=[low, high],
        baseline_name="single_shot_llm",
        baseline_score=0.45,
    )

    assert evaluation.baseline_name == "single_shot_llm"
    assert evaluation.baseline_score == 0.45
    assert evaluation.top_hypothesis_id == "hyp-high"
    assert evaluation.code_scientist_score > evaluation.baseline_score
    assert evaluation.beats_baseline is True
    assert evaluation.human_score_count == 0
    assert evaluation.benchmark_score_count == 0
    assert "Deterministic proxy" in evaluation.summary
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_evaluation.py::test_auto_capability_evaluation_scores_ranked_hypotheses_without_external_counts
```

Expected: FAIL because `evaluate_capability_proxy` does not exist.

- [x] **Step 3: Implement minimal proxy evaluator**

Add `evaluate_capability_proxy()` to `src/code_scientist/evaluation.py`:

```python
def evaluate_capability_proxy(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    baseline_name: str,
    baseline_score: float,
) -> CapabilityEvaluation:
    ranked = sorted(hypotheses, key=lambda item: item.elo, reverse=True)
    top = ranked[0] if ranked else None
    code_scientist_score = _proxy_capability_score(top) if top else 0.0
    beats_baseline = code_scientist_score > baseline_score
    summary = (
        f"Deterministic proxy capability evaluation: Code Scientist "
        f"{'beats' if beats_baseline else 'does not beat'} baseline "
        f"{baseline_name}: {code_scientist_score:.3f} vs {baseline_score:.3f}."
    )
    identity = f"{goal.id}:proxy:{baseline_name}:{baseline_score}:{code_scientist_score}:{top.id if top else ''}"
    return CapabilityEvaluation(
        id=stable_id("eval", identity),
        baseline_name=baseline_name,
        baseline_score=round(baseline_score, 3),
        code_scientist_score=round(code_scientist_score, 3),
        beats_baseline=beats_baseline,
        top_hypothesis_id=top.id if top else "",
        elo_human_correlation=0.0,
        elo_benchmark_correlation=0.0,
        candidate_count=len(hypotheses),
        summary=summary,
    )
```

Add `_proxy_capability_score(hypothesis)` nearby. It should be deterministic, bounded to `[0, 1]`, and use only inspectable run artifacts. Score components:

- base `0.35`
- `+0.15` when evidence refs exist
- `+0.15` when test-plan metrics exist
- `+0.10` when status is accepted
- `+0.10` when title/claim/rationale/test plan mentions benchmark, pass_rate, regression, or validation
- `+0.15` maximum Elo bonus from `(elo - 1200) / 400`

- [x] **Step 4: Verify focused evaluation test passes**

Run:

```bash
uv run pytest -q tests/test_evaluation.py::test_auto_capability_evaluation_scores_ranked_hypotheses_without_external_counts
```

Expected: PASS.

### Task 2: Study-Run Manifest Plumbing

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Write the failing CLI test**

Add `test_cli_study_run_can_auto_generate_capability_evaluation_for_scaling`:

```python
def test_cli_study_run_can_auto_generate_capability_evaluation_for_scaling(tmp_path, monkeypatch):
    def fake_run_research_cycle(**kwargs):
        out_dir = Path(kwargs["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        state = RunState(
            goal=ResearchGoal.from_objective(kwargs["objective"]),
            hypotheses=[
                Hypothesis(
                    id=f"hyp-{out_dir.name}",
                    title="Benchmark-grounded verifier",
                    claim="Use benchmark traces before accepting coding-agent patches.",
                    rationale="Evidence-backed verification should improve pass_rate without increasing regression_count.",
                    assumptions=["Benchmark traces are representative."],
                    evidence_refs=["ev-benchmark"],
                    test_plan=TestPlan(
                        experiment="Run repair benchmark.",
                        metrics=["pass_rate", "regression_count"],
                        success_condition="pass_rate improves without regression_count increasing",
                    ),
                    risks=["May overfit to benchmark traces."],
                    origin="generation",
                    elo=1460,
                    status="accepted",
                )
            ],
            task_queue=[Task(id=f"task-{out_dir.name}", kind="study", priority=1.0, status="completed")],
        )
        (out_dir / "state.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")
        return state

    monkeypatch.setattr(cli_module, "run_research_cycle", fake_run_research_cycle)
    manifest = tmp_path / "study.json"
    manifest.write_text(
        json.dumps(
            {
                "goals": [
                    {
                        "id": "auto-eval",
                        "objective": "Improve LLM coding agents with benchmark-grounded verification",
                        "auto_capability_eval": True,
                        "baseline_name": "single_shot_llm",
                        "baseline_score": 0.45,
                        "scaling_baseline_score": 0.45,
                        "scaling_label": "auto-eval-budget",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "study-runs"

    exit_code = main(["study-run", str(manifest), "--out", str(out_dir)])

    data = json.loads((out_dir / "auto-eval" / "state.json").read_text(encoding="utf-8"))
    study_report = (out_dir / "study.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert data["capability_evaluations"][0]["baseline_name"] == "single_shot_llm"
    assert data["capability_evaluations"][0]["top_hypothesis_id"] == "hyp-auto-eval"
    assert data["capability_evaluations"][0]["human_score_count"] == 0
    assert data["capability_evaluations"][0]["benchmark_score_count"] == 0
    assert data["scaling_curve"][0]["label"] == "auto-eval-budget"
    assert "Capability evaluations: 1" in study_report
    assert "benchmark scores" in study_report
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_cli.py::test_cli_study_run_can_auto_generate_capability_evaluation_for_scaling
```

Expected: FAIL because `StudyGoalSpec` does not parse the auto-eval fields and study-run cannot append proxy evaluations before scaling.

- [x] **Step 3: Implement manifest fields and append helper**

In `StudyGoalSpec`, add:

```python
auto_capability_eval: bool | None = None
baseline_name: str = ""
baseline_score: float | None = None
```

Import `evaluate_capability_proxy` from `code_scientist.evaluation`.

Parse the manifest fields in `_study_goals_from_manifest()`:

```python
auto_capability_eval=_optional_bool(raw_goal.get("auto_capability_eval"), f"goals[{index}].auto_capability_eval"),
baseline_name=str(raw_goal.get("baseline_name", "")).strip(),
baseline_score=_optional_float(raw_goal.get("baseline_score"), f"goals[{index}].baseline_score"),
```

Add `_append_auto_capability_evaluation(state, goal)` before `_append_scaling_curve_point()`. It should:

- return `state` unchanged unless `goal.auto_capability_eval` is true
- use `goal.baseline_score` or, if absent, `goal.scaling_baseline_score`
- raise `ValueError("Auto capability evaluation requires baseline_score or scaling_baseline_score.")` if neither exists
- default `baseline_name` to `"deterministic_single_shot_proxy"`
- append `evaluate_capability_proxy(...)` to `state.capability_evaluations`

- [x] **Step 4: Verify focused CLI test passes**

Run:

```bash
uv run pytest -q tests/test_cli.py::test_cli_study_run_can_auto_generate_capability_evaluation_for_scaling
```

Expected: PASS.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-study-run-auto-capability-eval.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 101 and revise the evaluation status to mention opt-in deterministic proxy capability evaluation for study-run manifests. Keep remaining gaps explicit: real human/benchmark/external evaluation is still required.

- [x] **Step 2: Mark this plan complete**

Replace task checkboxes with `[x]` after implementation and verification.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
rg -n "[[:blank:]]$" src/code_scientist/evaluation.py src/code_scientist/cli.py tests/test_evaluation.py tests/test_cli.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-study-run-auto-capability-eval.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
