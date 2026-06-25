# External Benchmark Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic external benchmark harness that compares saved baseline and Code Scientist states by running manifest-defined benchmark commands and normalizing their metrics into a `BenchmarkResult`.

**Architecture:** Extend `src/code_scientist/benchmarks.py` with a command-array based runner that writes arm-specific hypothesis JSON files, passes their paths through environment variables, accepts metrics from stdout or `CODE_SCIENTIST_METRICS_PATH`, and computes the existing benchmark deltas. Add a `code-scientist external-benchmark-comparison` CLI command for saved-state comparisons.

**Tech Stack:** Python standard library `subprocess`, existing `RunState`/`BenchmarkResult` models, pytest, `uv`.

---

### Task 1: External Benchmark Runner

**Files:**
- Modify: `tests/test_benchmarks.py`
- Modify: `src/code_scientist/benchmarks.py`

- [x] **Step 1: Write the failing runner test**

Add a test that creates a small Python benchmark script which reads `CODE_SCIENTIST_ARM`, `CODE_SCIENTIST_HYPOTHESES_PATH`, and `CODE_SCIENTIST_METRICS_PATH`, then writes required benchmark metrics. Call:

```python
result = run_external_benchmark_comparison(
    manifest,
    baseline_hypotheses,
    candidate_hypotheses,
    work_dir=tmp_path / "work",
)
```

Assert that baseline and candidate metrics came from the command output, deltas are computed, notes include both arm labels, and the arm hypothesis JSON files exist.

- [x] **Step 2: Write the failing validation test**

Add a test that supplies a manifest command as a string and assert:

```python
with pytest.raises(ValueError, match="command must be a non-empty list"):
    run_external_benchmark_comparison(manifest, [], [], work_dir=tmp_path / "work")
```

- [x] **Step 3: Run tests to verify red**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_run_external_benchmark_comparison_executes_arm_commands tests/test_benchmarks.py::test_run_external_benchmark_comparison_rejects_shell_string_commands -q
```

Expected: FAIL because `run_external_benchmark_comparison` is not implemented/exported.

- [x] **Step 4: Implement the minimal runner**

In `src/code_scientist/benchmarks.py`:

- Import `os`, `subprocess`, and `Mapping`.
- Add `run_external_benchmark_comparison(path, baseline_hypotheses, candidate_hypotheses, *, work_dir)`.
- Require a JSON manifest object with `baseline.command` and `candidate.command` as non-empty string lists.
- Write `baseline-hypotheses.json`, `candidate-hypotheses.json`, `baseline-metrics.json`, and `candidate-metrics.json` under `work_dir`.
- Run each command with no shell, manifest `env` merged into process env, and `CODE_SCIENTIST_ARM`, `CODE_SCIENTIST_HYPOTHESES_PATH`, `CODE_SCIENTIST_METRICS_PATH`.
- Parse metrics from metrics path when written, otherwise parse stdout JSON.
- Validate all `REQUIRED_BENCHMARK_METRICS` for both arms.
- Return a `BenchmarkResult` using `_is_successful`, with notes showing command completion for both arms plus manifest notes.

- [x] **Step 5: Run focused tests to verify green**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_run_external_benchmark_comparison_executes_arm_commands tests/test_benchmarks.py::test_run_external_benchmark_comparison_rejects_shell_string_commands -q
```

Expected: PASS.

### Task 2: CLI Command

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Write the failing CLI test**

Create baseline and candidate `RunState` JSON files, a benchmark manifest with a command script, and call:

```python
exit_code = main([
    "external-benchmark-comparison",
    str(manifest),
    "--baseline-state",
    str(baseline_state),
    "--candidate-state",
    str(candidate_state),
    "--work-dir",
    str(work_dir),
    "--out",
    str(output),
])
```

Assert `exit_code == 0`, output JSON exists, pass-rate delta is positive, and notes mention the external arm completion.

- [x] **Step 2: Run CLI test to verify red**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_external_benchmark_comparison_writes_result -q
```

Expected: FAIL because the CLI command is not registered.

- [x] **Step 3: Implement CLI wiring**

In `src/code_scientist/cli.py`:

- Import `run_external_benchmark_comparison`.
- Add an `external-benchmark-comparison` subparser with `manifest_json`, `--baseline-state`, `--candidate-state`, `--work-dir`, and `--out`.
- Load both states with `load_state`.
- Call the runner using state hypotheses and write `result.to_dict()` to `--out`.

- [x] **Step 4: Run focused CLI test to verify green**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_external_benchmark_comparison_writes_result -q
```

Expected: PASS.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-external-benchmark-comparison.md`

- [x] **Step 1: Update the roadmap**

Add slice 110 for generic external benchmark comparison. Update the evaluation row/status to say external benchmark command manifests can normalize saved-state baseline-vs-Code Scientist metrics, while preserving the remaining gap that no SWE-bench/GPQA-scale corpus has actually been run.

- [x] **Step 2: Mark plan checkboxes complete**

Mark this plan's checkboxes as complete only after the corresponding commands pass.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_run_external_benchmark_comparison_executes_arm_commands tests/test_benchmarks.py::test_run_external_benchmark_comparison_rejects_shell_string_commands tests/test_cli.py::test_cli_external_benchmark_comparison_writes_result -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
uv run code-scientist external-benchmark-comparison --help
```

Expected: all commands pass.
