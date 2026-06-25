# Benchmark Suite Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic benchmark-suite execution against produced hypotheses so benchmark artifacts can be generated from task cases instead of only loaded from precomputed aggregate fixtures.

**Architecture:** Extend `src/code_scientist/benchmarks.py` with a benchmark-suite loader/runner. A suite JSON contains baseline metrics, per-case required/forbidden terms, and optional per-case resource costs. The runner scans generated hypotheses, computes candidate pass rate and regression count, emits case-level notes, and returns a normal `BenchmarkResult`. Wire it through `code-scientist run --benchmark-suite` and `study-run` manifest `benchmark_suites`.

**Tech Stack:** Python, JSON fixtures, existing `BenchmarkResult`, argparse, pytest.

---

### Task 1: Failing Tests

**Files:**
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add benchmark runner test**

Add imports for `run_benchmark_suite` and `Hypothesis`/`TestPlan`. Create a suite with two cases:

```json
{
  "name": "Coding-agent benchmark suite",
  "baseline": {
    "pass_rate": 0.25,
    "regression_count": 2,
    "tool_calls": 8,
    "wall_time": 12,
    "cost": 0.24
  },
  "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
  "cases": [
    {"id": "retrieval", "required_terms": ["retrieved evidence", "regression"]},
    {"id": "blind-review", "required_terms": ["blind review"], "forbidden_terms": ["single prompt"]}
  ]
}
```

Use two hypotheses, one matching each case, and assert the result has:

```python
assert result.name == "Coding-agent benchmark suite"
assert result.candidate_metrics["pass_rate"] == 1.0
assert result.candidate_metrics["regression_count"] == 0.0
assert result.candidate_metrics["tool_calls"] == 4.0
assert result.deltas["pass_rate"] == 0.75
assert result.deltas["regression_count"] == -2.0
assert result.success is True
assert "retrieval: passed via hyp-retrieval" in result.notes
```

- [ ] **Step 2: Add CLI run test**

Add `test_cli_run_executes_benchmark_suite_against_generated_hypotheses`. Monkeypatch `run_research_cycle` to return a `RunState` with a matching hypothesis and the benchmark_results passed into the function. Run:

```bash
code-scientist run "Improve LLM coding agents" --benchmark-suite suite.json --out out-dir
```

Assert saved `state.json` contains a benchmark result with computed candidate pass rate.

- [ ] **Step 3: Verify red**

Run:

```bash
uv run pytest tests/test_benchmarks.py::test_run_benchmark_suite_scores_generated_hypotheses tests/test_cli.py::test_cli_run_executes_benchmark_suite_against_generated_hypotheses -q
```

Expected: FAIL because `run_benchmark_suite` and `--benchmark-suite` do not exist.

### Task 2: Implementation

**Files:**
- Modify: `src/code_scientist/benchmarks.py`
- Modify: `src/code_scientist/cli.py`

- [ ] **Step 1: Implement `run_benchmark_suite`**

Validate the suite object, load baseline metrics with existing `_metrics`, require non-empty `cases`, match case requirements against all hypothesis text, compute candidate metrics, deltas, success, and notes.

- [ ] **Step 2: Wire CLI run/study-run**

Import `run_benchmark_suite`, add `--benchmark-suite` to `run` and `study-run`, add `benchmark_suites` to `StudyGoalSpec`, parse manifest key `benchmark_suites`, and execute suites after the research state exists by appending benchmark results with produced hypotheses.

- [ ] **Step 3: Verify green**

Run the two focused tests again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update roadmap status**

Add slice 105 for deterministic benchmark-suite execution. Change the Evaluation row/status wording so it says benchmark suites can be executed against produced hypotheses, while preserving the remaining gap that there is still no SWE-bench/GPQA-scale external benchmark study.

- [ ] **Step 2: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands pass.
