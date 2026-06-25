# Feedback Loop Efficacy Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggregate measured feedback-loop before/after records across a capability study so the study report can analyze efficacy, not only count coverage.

**Architecture:** Extend `CapabilityStudySummary` with feedback-loop measurement count, positive-rate, mean delta, and per-metric mean deltas. Update `summarize_capability_study()` to accept optional feedback-loop evaluations and update `summarize_capability_study_from_states()` plus report rendering to pass and display them.

**Tech Stack:** Python dataclasses and pytest through `uv`, existing markdown report rendering.

---

### Task 1: Study Summary Aggregation

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `src/code_scientist/models.py`
- Modify: `src/code_scientist/evaluation.py`

- [ ] **Step 1: Write the failing test**

Add a test that calls `summarize_capability_study()` with measured and proxy `FeedbackLoopEvaluation` records. Assert only measured external records count, positive-rate is computed from per-record mean deltas, mean raw delta is computed across all measured deltas, and per-metric means are returned.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py::test_capability_study_summary_aggregates_feedback_loop_efficacy -q`

Expected: FAIL because `CapabilityStudySummary` lacks feedback-loop efficacy fields and `summarize_capability_study()` does not accept feedback-loop evaluations.

- [ ] **Step 3: Write minimal implementation**

Add these defaulted fields to `CapabilityStudySummary`: `feedback_loop_measurement_count`, `feedback_loop_positive_rate`, `feedback_loop_mean_delta`, and `feedback_loop_metric_deltas`. Update `from_dict()` for old state compatibility and compute the new fields from measured non-proxy feedback-loop evaluations.

- [ ] **Step 4: Run focused test**

Run: `uv run pytest tests/test_evaluation.py::test_capability_study_summary_aggregates_feedback_loop_efficacy -q`

Expected: PASS.

### Task 2: Report Rendering

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_reporting.py`
- Modify: `src/code_scientist/reporting.py`

- [ ] **Step 1: Write failing report tests**

Add assertions that `code-scientist study` output and per-run reports render feedback-loop measurement count, positive-rate, mean delta, and metric deltas.

- [ ] **Step 2: Run focused tests**

Run: `uv run pytest tests/test_cli.py::test_cli_study_aggregates_multiple_state_files tests/test_reporting.py::test_render_report_includes_capability_evaluation -q`

Expected: FAIL because the report does not render the new fields.

- [ ] **Step 3: Write minimal implementation**

Pass feedback-loop evaluations into `summarize_capability_study()` from both `render_capability_study_report()` and `render_report()`. Render the new lines when measured feedback-loop records exist.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_cli.py::test_cli_study_aggregates_multiple_state_files tests/test_reporting.py::test_render_report_includes_capability_evaluation -q`

Expected: PASS.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update roadmap documentation**

Record slice 86 as study-level feedback-loop efficacy aggregation and update the remaining gap to collecting real reviewer-score datasets at scale.

- [ ] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
PATH=/opt/homebrew/bin:$PATH npm test
PATH=/opt/homebrew/bin:$PATH npm run typecheck
PATH=/opt/homebrew/bin:$PATH npm run build
git diff --check
```

Expected: all commands exit 0.
