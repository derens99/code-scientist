# Feedback Loop Review Packets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate blinded feedback-loop reviewer packets and answer keys so real external reviewers can score baseline/observed artifacts without seeing which arm used meta-review feedback.

**Architecture:** Add an evaluation helper that consumes a JSON spec containing paired baseline and observed artifacts, then emits three JSON-compatible objects: a blinded reviewer packet, a private answer key, and a score template. Extend the existing feedback-loop review fixture loader so scored reviewer returns can use an inline answer key instead of exposing baseline/observed labels in each review item.

**Tech Stack:** Python CLI and JSON helpers with `uv`/pytest.

---

### Task 1: Packet Builder And Answer-Key Scoring

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `src/code_scientist/evaluation.py`

- [ ] **Step 1: Write the failing test**

Add a test that calls `build_feedback_loop_review_packet()` with one item containing `baseline_artifact` and `observed_artifact`. Assert the reviewer packet has anonymous `arm_a`/`arm_b` entries and no baseline/observed labels, the answer key records the hidden mapping, the score template contains empty metric slots, and `load_feedback_loop_review_fixture()` can score a returned fixture that supplies scores plus the private answer key.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py::test_build_feedback_loop_review_packet_blinds_arms_and_scores_with_answer_key -q`

Expected: FAIL because `build_feedback_loop_review_packet` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `build_feedback_loop_review_packet(data, seed="")`. Preserve metadata, deterministically assign each item's baseline/observed artifacts to `arm_a`/`arm_b`, emit an answer key keyed by item id, and emit a score template with `None` metric values for each arm. Extend `load_feedback_loop_review_fixture()` to read labels from top-level `answer_key` when item-level `baseline_label` / `observed_label` are absent.

- [ ] **Step 4: Run focused test**

Run: `uv run pytest tests/test_evaluation.py::test_build_feedback_loop_review_packet_blinds_arms_and_scores_with_answer_key -q`

Expected: PASS.

### Task 2: CLI Writer

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/code_scientist/cli.py`

- [ ] **Step 1: Write failing CLI test**

Add a test for `code-scientist feedback-loop-review-packet spec.json --out out-dir` that asserts it writes `review-packet.json`, `answer-key.json`, and `score-template.json`, and that the public packet does not expose the hidden baseline/observed labels.

- [ ] **Step 2: Run focused CLI test**

Run: `uv run pytest tests/test_cli.py::test_cli_feedback_loop_review_packet_writes_blinded_packet_template_and_key -q`

Expected: FAIL because the command does not exist.

- [ ] **Step 3: Write minimal implementation**

Add a `feedback-loop-review-packet` subcommand that loads the spec JSON, calls `build_feedback_loop_review_packet()`, writes the three files, and prints their paths.

- [ ] **Step 4: Run focused CLI test**

Run: `uv run pytest tests/test_cli.py::test_cli_feedback_loop_review_packet_writes_blinded_packet_template_and_key -q`

Expected: PASS.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update roadmap documentation**

Record slice 87 as blind reviewer packet generation and update the remaining feedback-loop gap to running the reviewer workflow on real datasets.

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
