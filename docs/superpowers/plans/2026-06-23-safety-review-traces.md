# Safety Review Traces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `safety_review` run an inspectable multi-turn safety exploration instead of relabeling the initial review.

**Architecture:** Reuse the existing `Review.review_trace` field so old state remains compatible and report/workbench rendering already works. Add deterministic safety turns for autonomy/deployment, data/credential exposure, and retrieved-source/tool-gaming risks; only force revision when the base hypothesis safety gate or retrieved evidence safety gate flags a concrete issue.

**Tech Stack:** Python dataclasses, `ReflectionAgent`, `EvidenceStore`, existing safety classifiers, pytest.

---

### Task 1: Safety Review Trace Behavior

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [ ] **Step 1: Write the failing test**

Add a test that calls `ReflectionAgent().review_with_type(..., "safety_review", store)` and asserts the review has turn-level trace lines for autonomy/deployment, data/credential exposure, and source/tool gaming.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest -q tests/test_agents.py::test_safety_review_records_multi_turn_red_team_trace`

Expected: FAIL because current `safety_review` has no `review_trace`.

- [ ] **Step 3: Implement minimal deterministic safety exploration**

Replace the current `safety_review` branch with a helper that retrieves safety evidence for three fixed turns, records evidence refs and trace observations, applies `review_hypothesis_safety`, applies `review_evidence_safety` to retrieved records, and returns a `Review` with `review_type="safety_review"`.

- [ ] **Step 4: Verify the focused test passes**

Run: `uv run pytest -q tests/test_agents.py::test_safety_review_records_multi_turn_red_team_trace`

Expected: PASS.

### Task 2: Documentation And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update the paper gap analysis**

Record the new completed slice and update the remaining safety gap to distinguish deterministic safety-review traces from full policy/governance coverage.

- [ ] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
git diff --check
```

Expected: all commands exit 0.
