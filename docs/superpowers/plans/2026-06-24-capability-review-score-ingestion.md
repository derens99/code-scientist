# Capability Review Score Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert scored blinded baseline-vs-Code Scientist capability review packets into persisted `CapabilityEvaluation` records.

**Architecture:** Add a loader in `src/code_scientist/evaluation.py` that reads `review_items[].scores`, unblinds labels through `answer_key`, normalizes metric scores by `human_rubric_scale`, averages baseline-arm scores into `baseline_score`, and maps Code Scientist arm scores to `hypothesis_id` human scores for `evaluate_capability`. Wire the loader through `code-scientist run --capability-review-fixture` and study-run manifest `capability_review_fixtures`.

**Tech Stack:** Python, argparse, pytest, dataclass `replace`, existing evaluation model.

---

### Task 1: Loader And CLI Tests

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing loader test**

Add `load_capability_review_fixture` to `tests/test_evaluation.py` imports and add a test that:
- Builds a blinded packet with `build_capability_review_packet`.
- Creates a scored fixture by merging `score_template`, `answer_key`, and reviewer scores for the answer-key labels.
- Calls `load_capability_review_fixture(scored_fixture, goal, [low, high])`.
- Asserts the result has `baseline_score == 0.6`, `code_scientist_score == 0.9`, `human_score_count == 1`, `human_rubric_judgment_count == 1`, and the rubric criteria from the scored metrics.

- [ ] **Step 2: Write the failing CLI append test**

Add a `test_cli_run_accepts_capability_review_fixture_scores` test that monkeypatches `cli_module.run_research_cycle` to return a `RunState` with one matching hypothesis, calls:

```bash
code-scientist run "Improve LLM coding agents" --capability-review-fixture scored.json --out out-dir
```

Then assert saved `state.json` contains a capability evaluation with the expected `baseline_name`, `baseline_score`, `code_scientist_score`, and human rubric judgment count.

- [ ] **Step 3: Verify red**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_load_capability_review_fixture_unblinds_scored_arm_scores tests/test_cli.py::test_cli_run_accepts_capability_review_fixture_scores -q
```

Expected: FAIL because the loader and CLI option do not exist.

### Task 2: Loader And CLI Implementation

**Files:**
- Modify: `src/code_scientist/evaluation.py`
- Modify: `src/code_scientist/cli.py`

- [ ] **Step 1: Implement `load_capability_review_fixture` and list loader**

Validate the scored JSON object, require non-empty `review_items`, require answer-key labels either inline or under top-level `answer_key`, normalize shared metric scores by `human_rubric_scale`, and call `evaluate_capability`.

- [ ] **Step 2: Wire CLI run and study-run**

Import `load_capability_review_fixtures`, add `--capability-review-fixture`, add `StudyGoalSpec.capability_review_fixtures`, parse manifest key `capability_review_fixtures`, append review-derived evaluations after each run, and include them before scaling-point generation.

- [ ] **Step 3: Verify green**

Run the two focused tests again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update roadmap status**

Change the backend test count after full tests pass. Add slice 103 for scored capability-review ingestion and remove the specific "no ingestion path for returned capability-review arm scores" gap while preserving broader missing real-study/statistical-validation gaps.

- [ ] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands pass.
