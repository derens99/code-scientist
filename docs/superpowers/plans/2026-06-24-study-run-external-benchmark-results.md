# Study Run External Benchmark Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make external benchmark command results first-class evidence in `code-scientist study-run` capability studies.

**Architecture:** Reuse the external benchmark runner from `src/code_scientist/benchmarks.py`. `study-run` will accept global and per-goal external benchmark manifests, generate a deterministic baseline arm for each goal that needs external comparisons, append the resulting `BenchmarkResult` records to the Code Scientist run state, and the capability-study coverage audit will count benchmark result artifacts separately from per-candidate benchmark score fixtures.

**Tech Stack:** Python CLI, existing dataclasses/serialization, pytest, `uv`.

---

### Task 1: Coverage Counts Benchmark Result Artifacts

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `src/code_scientist/models.py`
- Modify: `src/code_scientist/evaluation.py`
- Modify: `src/code_scientist/reporting.py`

- [x] **Step 1: Write the failing coverage test**

In `test_capability_study_coverage_audits_paper_evaluation_requirements`, set `benchmark_score_count=0` on the complete state's `CapabilityEvaluation`, add a `BenchmarkResult` to `complete.benchmark_results`, and assert:

```python
assert complete_coverage.benchmark_scored_candidate_count == 0
assert complete_coverage.benchmark_result_count == 1
assert complete_coverage.passed is True
```

Also update the report assertion in `tests/test_cli.py::test_cli_study_report_renders_capability_statistics_and_coverage` or an adjacent report test to expect:

```python
assert "Benchmark result artifacts:" in report
```

- [x] **Step 2: Run coverage tests to verify red**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_capability_study_coverage_audits_paper_evaluation_requirements tests/test_cli.py::test_cli_study_report_renders_capability_statistics_and_coverage -q
```

Expected: FAIL because `CapabilityStudyCoverage` has no `benchmark_result_count` and reports do not render it.

- [x] **Step 3: Implement coverage model and audit**

In `CapabilityStudyCoverage`, add:

```python
benchmark_result_count: int
```

Add a `from_dict` default of `0`.

In `audit_capability_study_coverage`, compute:

```python
benchmark_result_count = sum(len(state.benchmark_results) for state in states)
```

Only add the benchmark missing requirement when both `benchmark_scored_candidate_count <= 0` and `benchmark_result_count <= 0`.

In `render_capability_study_report`, add:

```python
f"- Benchmark result artifacts: {coverage.benchmark_result_count}",
```

- [x] **Step 4: Run focused coverage tests to verify green**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_capability_study_coverage_audits_paper_evaluation_requirements tests/test_cli.py::test_cli_study_report_renders_capability_statistics_and_coverage -q
```

Expected: PASS.

### Task 2: Study-Run Executes External Benchmark Manifests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Write the failing study-run test**

Add `test_cli_study_run_executes_external_benchmark_manifests_and_records_coverage`. It should:

- Monkeypatch `cli_module.run_research_cycle` to return a run state with one candidate hypothesis.
- Create an external benchmark command script that reads the hypothesis input env vars and writes metrics to `CODE_SCIENTIST_METRICS_PATH`.
- Create a study manifest with one goal containing `external_benchmark_manifests`.
- Run:

```python
exit_code = main(["study-run", str(manifest), "--out", str(out_dir)])
```

- Assert:

```python
assert state["benchmark_results"][0]["name"] == "Study-run external benchmark"
assert state["benchmark_results"][0]["deltas"]["pass_rate"] == 0.5
assert (out_dir / "retrieval" / "baseline" / "state.json").exists()
assert (out_dir / "retrieval" / "external-benchmarks" / "external-manifest" / "candidate-hypotheses.json").exists()
assert "Benchmark result artifacts: 1" in study_report
```

- [x] **Step 2: Run the study-run test to verify red**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_study_run_executes_external_benchmark_manifests_and_records_coverage -q
```

Expected: FAIL because `study-run` ignores `external_benchmark_manifests`.

- [x] **Step 3: Implement study-run external benchmark append**

In `build_parser`, add to `study_run_parser`:

```python
study_run_parser.add_argument("--external-benchmark-manifest", action="append", default=[])
```

Add helper:

```python
def _append_external_benchmark_results(state, manifest_path, global_manifest_paths, goal, run_dir):
    external_paths = _external_benchmark_manifest_paths_for_goal(manifest_path, global_manifest_paths, goal)
    if not external_paths:
        return state
    baseline_dir = run_dir / "baseline"
    baseline_state = run_baseline_research(
        goal.objective,
        method=goal.baseline_method,
        max_hypotheses=goal.baseline_max_hypotheses,
    )
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "state.json").write_text(json.dumps(baseline_state.to_dict(), indent=2), encoding="utf-8")
    (baseline_dir / "report.md").write_text(render_report(baseline_state), encoding="utf-8")
    results = [
        run_external_benchmark_comparison(
            external_path,
            baseline_state.hypotheses,
            state.hypotheses,
            work_dir=run_dir / "external-benchmarks" / _safe_slug(external_path.stem),
        )
        for external_path in external_paths
    ]
    return replace(state, benchmark_results=[*state.benchmark_results, *results])
```

Call it in the `study-run` branch after `_append_benchmark_suite_results` and before report writing.

- [x] **Step 4: Run focused study-run test to verify green**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_study_run_executes_external_benchmark_manifests_and_records_coverage -q
```

Expected: PASS.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-study-run-external-benchmark-results.md`

- [x] **Step 1: Update roadmap**

Add slice 112 for `study-run` external benchmark result integration. Update the Phase 6 status and remaining-gap wording so external command benchmark artifacts are recognized as capability-study evidence, while still making clear that no large external corpus study has been run.

- [x] **Step 2: Mark plan complete**

Mark checkboxes complete only after the corresponding red, green, and full verification steps have passed.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_capability_study_coverage_audits_paper_evaluation_requirements tests/test_cli.py::test_cli_study_report_renders_capability_statistics_and_coverage tests/test_cli.py::test_cli_study_run_executes_external_benchmark_manifests_and_records_coverage -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
uv run code-scientist study-run --help
```

Expected: all commands pass.
