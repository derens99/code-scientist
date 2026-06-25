# Benchmark Study Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-command benchmark study runner that creates baseline and Code Scientist arms, scores them against benchmark suites, and writes aggregate benchmark comparison artifacts.

**Architecture:** Reuse `run_baseline_research`, `run_research_cycle`, `run_benchmark_suite_comparison`, `summarize_benchmark_comparison_study`, and `render_benchmark_comparison_study_report`. Add a `code-scientist benchmark-study-run` command that reads a `goals` manifest, writes per-goal `baseline/state.json` and `code-scientist/state.json`, runs suite comparisons for each goal, and writes top-level `benchmark-comparisons.json` plus `benchmark-study.md`.

**Tech Stack:** Python, existing `RunState`, JSON manifests, argparse, pytest.

---

### Task 1: Failing Test

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add CLI benchmark study-run test**

Add `test_cli_benchmark_study_run_executes_baseline_candidate_and_comparison`. Monkeypatch `cli_module.run_research_cycle` to return a candidate `RunState` containing a hypothesis that matches the benchmark suite. Create a suite:

```json
{
  "name": "Study suite",
  "cases": [
    {"id": "retrieval", "required_terms": ["retrieved evidence", "regression"]}
  ]
}
```

Create a manifest:

```json
{
  "goals": [
    {
      "id": "retrieval",
      "objective": "Improve LLM coding agents with retrieved evidence",
      "benchmark_suites": ["suite.json"],
      "baseline_max_hypotheses": 1
    }
  ]
}
```

Run:

```python
exit_code = main([
    "benchmark-study-run",
    str(manifest),
    "--cycles",
    "1",
    "--max-hypotheses",
    "2",
    "--max-matches",
    "1",
    "--out",
    str(out_dir),
])
```

Assert:

```python
assert exit_code == 0
assert (out_dir / "retrieval" / "baseline" / "state.json").exists()
assert (out_dir / "retrieval" / "code-scientist" / "state.json").exists()
assert output["summary"]["comparison_count"] == 1
assert output["summary"]["success_count"] == 1
assert output["results"][0]["baseline_metrics"]["pass_rate"] == 0.0
assert output["results"][0]["candidate_metrics"]["pass_rate"] == 1.0
assert "Code Scientist Benchmark Comparison Study" in report
```

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_benchmark_study_run_executes_baseline_candidate_and_comparison -q
```

Expected: FAIL because `benchmark-study-run` is not registered.

### Task 2: Implementation

**Files:**
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Extend `StudyGoalSpec` baseline fields**

Add:

```python
baseline_method: str = "single_shot"
baseline_max_hypotheses: int = 1
```

Parse `baseline_method` and `baseline_max_hypotheses` from each manifest goal.

- [x] **Step 2: Add parser command**

Add `benchmark-study-run` with:

```bash
code-scientist benchmark-study-run manifest.json \
  --cycles 1 \
  --max-hypotheses 6 \
  --max-matches 4 \
  --provider deterministic \
  --model MODEL \
  --max-tokens 4096 \
  --env-file .env \
  --benchmark-suite suite.json \
  --out out-dir
```

- [x] **Step 3: Implement handler**

For each manifest goal:

1. Create `out/<goal-id>/baseline/state.json` and report via `run_baseline_research`.
2. Create `out/<goal-id>/code-scientist/state.json` and report via `run_research_cycle`.
3. Compare each global and per-goal benchmark suite with `run_benchmark_suite_comparison`.
4. Append results to a top-level list.

Write:

```text
out/benchmark-comparisons.json
out/benchmark-study.md
```

Use the same JSON shape as `benchmark-comparison-study`.

- [x] **Step 4: Verify green**

Run the focused test again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [x] **Step 1: Update roadmap status**

Add slice 109 for one-command benchmark study execution. Update the Evaluation row/status wording to say the system can now generate baseline and Code Scientist arms plus aggregate comparisons from one manifest, while preserving the remaining gap that no real external benchmark corpus study has been run.

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
