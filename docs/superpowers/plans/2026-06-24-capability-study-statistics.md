# Capability Study Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit statistical readouts to capability-study aggregation so baseline comparisons are not reported only as averages.

**Architecture:** Extend `CapabilityStudySummary` with score-delta sample count, sample standard deviation, standard error, 95% normal-approximation confidence interval, paired standardized effect size, and a two-sided binomial sign-test p-value for baseline wins. Compute these in `summarize_capability_study`, render them in capability-study reports and per-run reports, and keep backwards-compatible defaults for existing JSON.

**Tech Stack:** Python dataclasses, standard-library math, pytest, existing markdown reporting.

---

### Task 1: Failing Tests

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_reporting.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add a failing evaluation test**

Add `test_capability_study_summary_reports_score_delta_statistics` with four `CapabilityEvaluation` records whose deltas are `0.1`, `0.2`, `0.3`, and `0.4`. Assert:

```python
assert summary.score_delta_count == 4
assert summary.score_delta_stddev == 0.129
assert summary.score_delta_standard_error == 0.065
assert summary.score_delta_ci_low == 0.124
assert summary.score_delta_ci_high == 0.376
assert summary.score_delta_effect_size == 1.936
assert summary.baseline_win_sign_test_p_value == 0.125
```

- [ ] **Step 2: Add failing report assertions**

In `test_render_report_includes_capability_evaluation_and_study_summary`, assert the report contains `Score delta 95% CI` and `Baseline win sign-test p-value`.

- [ ] **Step 3: Add failing CLI study assertions**

In `test_cli_study_aggregates_multiple_state_files`, assert the study markdown contains `Score delta 95% CI` and `Baseline win sign-test p-value`.

- [ ] **Step 4: Verify red**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_capability_study_summary_reports_score_delta_statistics tests/test_reporting.py::test_render_report_includes_capability_evaluation_and_study_summary tests/test_cli.py::test_cli_study_aggregates_multiple_state_files -q
```

Expected: FAIL because the new statistical fields and report lines do not exist.

### Task 2: Implementation

**Files:**
- Modify: `src/code_scientist/models.py`
- Modify: `src/code_scientist/evaluation.py`
- Modify: `src/code_scientist/reporting.py`

- [ ] **Step 1: Extend `CapabilityStudySummary`**

Add defaulted fields:

```python
score_delta_count: int = 0
score_delta_stddev: float = 0.0
score_delta_standard_error: float = 0.0
score_delta_ci_low: float = 0.0
score_delta_ci_high: float = 0.0
score_delta_effect_size: float = 0.0
baseline_win_sign_test_p_value: float = 1.0
```

Update `from_dict` with the same defaults.

- [ ] **Step 2: Compute statistics in `summarize_capability_study`**

Create score deltas from `code_scientist_score - baseline_score`, then compute:
- sample standard deviation for `n >= 2`
- standard error as `stddev / sqrt(n)`
- normal 95% interval as `mean +/- 1.96 * se`
- effect size as `mean / stddev` when `stddev > 0`
- two-sided sign-test p-value from non-tie wins/losses under p=0.5

- [ ] **Step 3: Render statistics**

Render the new values in both `render_capability_study_report` and the regular report capability-study section.

- [ ] **Step 4: Verify green**

Run the focused tests again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update roadmap status**

Add slice 104 for capability-study statistics, update the status wording, and remove the broad “no statistical analysis” wording while preserving the remaining gap that there is not yet a completed large external study.

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
