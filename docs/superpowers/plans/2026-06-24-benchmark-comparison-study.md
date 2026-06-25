# Benchmark Comparison Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manifest-driven benchmark comparison study command that runs multiple baseline-vs-Code Scientist benchmark-suite comparisons and writes aggregate machine-readable and markdown study artifacts.

**Architecture:** Reuse `run_benchmark_suite_comparison` and existing `BenchmarkResult` serialization. Add a lightweight summary helper in `src/code_scientist/benchmarks.py`, a markdown renderer in `src/code_scientist/reporting.py`, and a `code-scientist benchmark-comparison-study` CLI command that loads a manifest of comparison specs, runs each saved-state comparison, and writes `benchmark-comparisons.json` plus `benchmark-study.md`.

**Tech Stack:** Python, JSON manifests, argparse, existing `BenchmarkResult`, pytest.

---

### Task 1: Failing Tests

**Files:**
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_reporting.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add summary helper test**

Add a test that creates two `BenchmarkResult` records and calls:

```python
summary = summarize_benchmark_comparison_study([first, second])
```

Assert exact fields:

```python
assert summary["comparison_count"] == 2
assert summary["success_count"] == 1
assert summary["success_rate"] == 0.5
assert summary["mean_pass_rate_delta"] == 0.25
assert summary["total_regression_delta"] == -1.0
assert summary["mean_tool_calls_delta"] == 1.5
assert summary["mean_wall_time_delta"] == -0.5
assert summary["mean_cost_delta"] == 0.01
```

- [x] **Step 2: Add report renderer test**

Add a test for:

```python
report = render_benchmark_comparison_study_report([first, second])
```

Assert the report contains:

```python
"# Code Scientist Benchmark Comparison Study"
"- Comparisons: 2"
"- Success rate: 0.500"
"- Mean pass-rate delta: +0.25"
"## Comparison Results"
"Retrieval suite"
```

- [x] **Step 3: Add CLI manifest test**

Write one suite JSON, baseline/candidate `RunState` files for one winning comparison and one non-winning comparison, then a manifest:

```json
{
  "comparisons": [
    {
      "id": "retrieval",
      "suite": "suite.json",
      "baseline_state": "baseline.state.json",
      "candidate_state": "candidate.state.json",
      "baseline_name": "single_shot",
      "candidate_name": "code_scientist"
    }
  ]
}
```

Run:

```bash
uv run code-scientist benchmark-comparison-study manifest.json --out out-dir
```

Assert `benchmark-comparisons.json` and `benchmark-study.md` exist, JSON includes summary/results, and markdown includes aggregate deltas.

- [x] **Step 4: Verify red**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_summarize_benchmark_comparison_study_aggregates_results tests/test_reporting.py::test_render_benchmark_comparison_study_report_summarizes_results tests/test_cli.py::test_cli_benchmark_comparison_study_writes_results_and_report -q
```

Expected: FAIL because the summary helper, renderer, and CLI command do not exist.

### Task 2: Implementation

**Files:**
- Modify: `src/code_scientist/benchmarks.py`
- Modify: `src/code_scientist/reporting.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Implement summary helper**

Add:

```python
def summarize_benchmark_comparison_study(results: list[BenchmarkResult]) -> dict[str, float | int]:
    ...
```

It should calculate count, success count/rate, mean pass-rate delta, total regression delta, mean tool-call delta, mean wall-time delta, and mean cost delta. Empty results should return zero values.

- [x] **Step 2: Implement markdown renderer**

Add:

```python
def render_benchmark_comparison_study_report(
    results: list[BenchmarkResult],
    summary: dict[str, float | int] | None = None,
) -> str:
    ...
```

Use existing `_format_delta` for signed values. Include an aggregate summary and one bullet per comparison.

- [x] **Step 3: Implement CLI command**

Add `benchmark-comparison-study` to `build_parser`, parse a manifest object with non-empty `comparisons`, load each baseline/candidate state, call `run_benchmark_suite_comparison`, then write:

```text
out-dir/benchmark-comparisons.json
out-dir/benchmark-study.md
```

The JSON shape should be:

```json
{"summary": {...}, "results": [...]}
```

- [x] **Step 4: Verify green**

Run the focused test command again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [x] **Step 1: Update roadmap status**

Add slice 107 for manifest-driven benchmark comparison studies. Update the Evaluation row/status wording to say the repo can batch saved-state comparisons into aggregate study artifacts, while preserving the remaining gap that no completed external benchmark corpus study has been run.

- [x] **Step 2: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands pass.
