# Feedback Loop Blind Review Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a blind-review feedback-loop study ingestion path that computes measured before/after quality from reviewer item scores instead of requiring pre-aggregated metrics.

**Architecture:** Reuse `FeedbackLoopEvaluation` as the persisted output, but add a separate loader for raw blind-review score fixtures. Wire that loader into `run`, `study-run`, and the workbench start-run path so real reviewer packets can be scored and aggregated by existing study coverage/reporting.

**Tech Stack:** Python dataclasses/CLI with `uv`, pytest, Next.js/TypeScript with Vitest.

---

### Task 1: Blind Review Score Loader

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `src/code_scientist/evaluation.py`

- [ ] **Step 1: Write the failing test**

```python
def test_load_feedback_loop_review_fixture_aggregates_blind_item_scores(tmp_path):
    fixture = tmp_path / "feedback-loop-review.json"
    fixture.write_text(
        json.dumps(
            {
                "cycle": 4,
                "source_meta_review_id": "meta-review-3",
                "feedback_agents": ["generation", "ranking"],
                "feedback_item_count": 4,
                "adopted_feedback_count": 3,
                "measurement_source": "maintainer_blind_review",
                "artifact_refs": ["review-packet.json", "reviewer-scores.json"],
                "review_items": [
                    {
                        "item_id": "item-1",
                        "baseline_label": "arm_red",
                        "observed_label": "arm_blue",
                        "scores": {
                            "arm_red": {"expert_score": 3, "accepted": 0},
                            "arm_blue": {"expert_score": 5, "accepted": 1},
                        },
                    },
                    {
                        "item_id": "item-2",
                        "baseline_label": "arm_blue",
                        "observed_label": "arm_red",
                        "scores": {
                            "arm_blue": {"expert_score": 4, "accepted": 0},
                            "arm_red": {"expert_score": 5, "accepted": 1},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_feedback_loop_review_fixture(fixture)

    assert evaluation.measurement_status == "measured"
    assert evaluation.measurement_source == "maintainer_blind_review"
    assert evaluation.baseline_quality == {"accepted": 0.0, "expert_score": 3.5}
    assert evaluation.observed_quality == {"accepted": 1.0, "expert_score": 5.0}
    assert evaluation.deltas == {"accepted": 1.0, "expert_score": 1.5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py::test_load_feedback_loop_review_fixture_aggregates_blind_item_scores -q`

Expected: FAIL because `load_feedback_loop_review_fixture` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add `load_feedback_loop_review_fixture()` and `load_feedback_loop_review_fixtures()` to `src/code_scientist/evaluation.py`. Parse `review_items`, map each item's `baseline_label` and `observed_label` through its `scores`, average metric values per arm, compute shared deltas, and emit a measured `FeedbackLoopEvaluation`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py::test_load_feedback_loop_review_fixture_aggregates_blind_item_scores -q`

Expected: PASS.

### Task 2: CLI And Study-Run Wiring

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/code_scientist/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests proving `code-scientist run --feedback-loop-review-fixture` appends a measured evaluation to `state.json`, and `study-run` accepts `feedback_loop_review_fixtures` in a per-goal manifest.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_cli_run_persists_feedback_loop_review_fixtures tests/test_cli.py::test_cli_study_run_appends_feedback_loop_review_fixtures -q`

Expected: FAIL because the new flag and manifest key are not wired.

- [ ] **Step 3: Write minimal implementation**

Add `--feedback-loop-review-fixture`, `StudyGoalSpec.feedback_loop_review_fixtures`, manifest parsing, and append logic that merges aggregate feedback-loop fixtures with blind-review score fixtures.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_cli_run_persists_feedback_loop_review_fixtures tests/test_cli.py::test_cli_study_run_appends_feedback_loop_review_fixtures -q`

Expected: PASS.

### Task 3: Workbench Wiring And Documentation

**Files:**
- Modify: `web/src/lib/codeScientist.test.ts`
- Modify: `web/src/lib/codeScientist.ts`
- Modify: `web/src/lib/client.ts`
- Modify: `web/src/app/api/runs/start/route.ts`
- Modify: `web/src/components/RunSetup.test.ts`
- Modify: `web/src/components/RunSetup.tsx`
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Write failing frontend tests**

Add a `feedbackLoopReviewPaths` case to `buildRunArgs` and assert the setup form includes `Feedback-loop blind review fixtures`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PATH=/opt/homebrew/bin:$PATH npm test -- RunSetup.test.ts codeScientist.test.ts`

Expected: FAIL because the workbench does not expose the new path.

- [ ] **Step 3: Write minimal implementation and docs**

Thread `feedbackLoopReviewPaths` through the start-run payload, API cleaner, CLI argument builder, and run setup textarea. Update the paper gap analysis with slice 85 and narrow the remaining feedback-loop gap to collecting real reviewer scores at scale.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
uv run pytest -q
PATH=/opt/homebrew/bin:$PATH npm test
PATH=/opt/homebrew/bin:$PATH npm run typecheck
PATH=/opt/homebrew/bin:$PATH npm run build
git diff --check
```

Expected: all commands exit 0.
