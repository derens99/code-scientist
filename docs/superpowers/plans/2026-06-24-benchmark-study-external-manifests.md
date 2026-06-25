# Benchmark Study External Manifests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `code-scientist benchmark-study-run` execute external benchmark command manifests after generating baseline and Code Scientist arms, so one manifest can run a local multi-goal external benchmark study.

**Architecture:** Extend `StudyGoalSpec` with `external_benchmark_manifests`, add a global `--external-benchmark-manifest` option, resolve manifest paths relative to the study manifest, and call `run_external_benchmark_comparison` with per-goal work directories under `out/<goal-id>/external-benchmarks/<manifest-stem>`. Keep deterministic benchmark-suite comparisons working and require at least one suite or external manifest per goal.

**Tech Stack:** Python CLI, existing `RunState`/`BenchmarkResult` models, `subprocess`-based external benchmark runner, pytest, `uv`.

---

### Task 1: Study-Run External Benchmark Test

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write the failing per-goal external manifest test**

Add a test named `test_cli_benchmark_study_run_executes_external_benchmark_manifests`. The test should:

- Create an `external_runner.py` script that reads `CODE_SCIENTIST_ARM`, `CODE_SCIENTIST_HYPOTHESES_PATH`, and `CODE_SCIENTIST_METRICS_PATH`.
- Write required metrics to `CODE_SCIENTIST_METRICS_PATH` with baseline pass rate `0.25` and candidate pass rate `0.75`.
- Monkeypatch `cli_module.run_research_cycle` so the Code Scientist arm returns a candidate state with one hypothesis.
- Create a `benchmark-study.json` manifest containing one goal with `external_benchmark_manifests: [external-manifest.json]` and no `benchmark_suites`.
- Run `main(["benchmark-study-run", str(manifest), "--out", str(out_dir)])`.
- Assert:

```python
assert output["summary"]["comparison_count"] == 1
assert output["summary"]["success_count"] == 1
assert output["results"][0]["name"] == "External study fixture"
assert output["results"][0]["deltas"]["pass_rate"] == 0.5
assert (out_dir / "retrieval" / "external-benchmarks" / "external-manifest" / "baseline-hypotheses.json").exists()
assert "External study fixture" in report
```

- [x] **Step 2: Run the test to verify red**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_benchmark_study_run_executes_external_benchmark_manifests -q
```

Expected: FAIL because `external_benchmark_manifests` is not parsed and `benchmark-study-run` still requires a benchmark suite.

### Task 2: CLI And Manifest Implementation

**Files:**
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Add manifest field and parser option**

In `StudyGoalSpec`, add:

```python
external_benchmark_manifests: list[str] = field(default_factory=list)
```

In `build_parser`, add to `benchmark-study-run`:

```python
benchmark_study_run_parser.add_argument("--external-benchmark-manifest", action="append", default=[])
```

In `_study_goals_from_manifest`, parse:

```python
external_benchmark_manifests=_string_list(
    raw_goal.get("external_benchmark_manifests"),
    f"goals[{index}].external_benchmark_manifests",
)
```

- [x] **Step 2: Add external manifest path resolution**

Add:

```python
def _external_benchmark_manifest_paths_for_goal(
    manifest_path: Path,
    global_manifest_paths: list[str],
    goal: StudyGoalSpec,
) -> list[Path]:
    paths: list[Path] = []
    for raw_path in global_manifest_paths:
        if str(raw_path).strip():
            paths.append(Path(raw_path))
    for raw_path in goal.external_benchmark_manifests:
        if str(raw_path).strip():
            paths.append(_resolve_manifest_path(manifest_path, raw_path))
    return paths
```

- [x] **Step 3: Wire `benchmark-study-run`**

Inside the goal loop:

```python
external_manifest_paths = _external_benchmark_manifest_paths_for_goal(
    manifest_path,
    args.external_benchmark_manifest,
    goal,
)
if not suite_paths and not external_manifest_paths:
    raise ValueError(
        f"Benchmark study goal {goal.id} must include at least one benchmark suite or external benchmark manifest."
    )
```

After suite comparisons, run:

```python
for external_manifest_path in external_manifest_paths:
    external_work_dir = run_dir / "external-benchmarks" / _safe_slug(external_manifest_path.stem)
    results.append(
        run_external_benchmark_comparison(
            external_manifest_path,
            baseline_state.hypotheses,
            candidate_state.hypotheses,
            work_dir=external_work_dir,
        )
    )
```

- [x] **Step 4: Run focused test to verify green**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_benchmark_study_run_executes_external_benchmark_manifests -q
```

Expected: PASS.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-benchmark-study-external-manifests.md`

- [x] **Step 1: Update roadmap**

Add slice 111 for manifest-driven external benchmark study execution. Update the evaluation row/status so it says `benchmark-study-run` can run local external command manifests after generating study arms, while preserving the remaining gap that no SWE-bench/GPQA-scale corpus has actually been run.

- [x] **Step 2: Mark this plan complete**

Mark checkboxes complete after the corresponding focused and full verification commands pass.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_benchmark_study_run_executes_external_benchmark_manifests tests/test_cli.py::test_cli_benchmark_study_run_executes_baseline_candidate_and_comparison tests/test_benchmarks.py::test_run_external_benchmark_comparison_executes_arm_commands -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
uv run code-scientist benchmark-study-run --help
```

Expected: all commands pass.
