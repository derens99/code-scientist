# Benchmark Suite Baseline Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a saved-state benchmark-suite comparison path so baseline and Code Scientist runs can be scored against identical benchmark cases without hand-authored aggregate baseline metrics.

**Architecture:** Reuse the deterministic benchmark-suite case matcher in `src/code_scientist/benchmarks.py`. Add `run_benchmark_suite_comparison` to compute baseline and candidate metrics from two hypothesis lists, then expose it through `code-scientist benchmark-suite-comparison SUITE_JSON --baseline-state baseline.state.json --candidate-state candidate.state.json --out comparison.json`.

**Tech Stack:** Python, JSON fixtures, existing `BenchmarkResult`, argparse, pytest.

---

### Task 1: Failing Tests

**Files:**
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add benchmark comparison unit test**

Create a suite with explicit benchmark cases and no aggregate `baseline` metrics. Pass one baseline hypothesis set and one Code Scientist hypothesis set. Assert the result computes baseline pass rate, candidate pass rate, deltas, success, resource costs, and per-case baseline/candidate notes.

- [x] **Step 2: Add CLI comparison test**

Write baseline and candidate `RunState` JSON files, run:

```bash
code-scientist benchmark-suite-comparison suite.json \
  --baseline-state baseline.state.json \
  --candidate-state candidate.state.json \
  --out comparison.json
```

Assert the output JSON is a normal `BenchmarkResult` with computed deltas.

- [x] **Step 3: Verify red**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_run_benchmark_suite_comparison_scores_baseline_and_candidate_hypotheses tests/test_cli.py::test_cli_benchmark_suite_comparison_writes_result_from_two_states -q
```

Expected: fail because the comparison API and CLI command do not exist.

### Task 2: Implementation

**Files:**
- Modify: `src/code_scientist/benchmarks.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Extract suite scoring helper**

Refactor benchmark-suite scoring so the same required/forbidden-term case logic can score any hypothesis list.

- [x] **Step 2: Implement saved-state comparison**

Add `run_benchmark_suite_comparison` with optional `baseline_case_cost` and `candidate_case_cost`, falling back to shared `case_cost`.

- [x] **Step 3: Wire CLI command**

Add `benchmark-suite-comparison`, load both states with `load_state`, score both hypothesis sets, and write the result JSON.

- [x] **Step 4: Verify green**

Run the focused tests again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [x] **Step 1: Update roadmap status**

Add slice 106 for saved-state benchmark-suite comparison and clarify that the remaining gap is a completed large external benchmark study, not just the ability to compare two saved runs.

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
