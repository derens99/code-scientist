# Proximity Dedup Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn proximity deduplication controls into persisted hypothesis merge decisions that affect ranking/evolution and are visible in reports and the workbench.

**Architecture:** Extend `Hypothesis` with backwards-compatible proximity decision metadata: `merged_into` and `proximity_notes`. Add a supervisor helper that applies high-confidence deduplication edges by marking the lower-priority hypothesis as `merged_duplicate`, keeping the representative accepted, and preserving diversity notes without discarding hypotheses from state. Exclude merged duplicates from future pair scheduling and leader evolution while reporting the decision in markdown and UI.

**Tech Stack:** Python dataclasses, pytest, supervisor state JSON, markdown report rendering, Next.js/React/Vitest.

---

### Task 1: Hypothesis Proximity Decision Metadata

**Files:**
- Modify: `src/code_scientist/models.py`
- Modify: `web/src/lib/types.ts`
- Test: `tests/test_models.py`

- [x] **Step 1: Write failing model test**

Require `Hypothesis.from_dict` to round-trip `merged_into` and `proximity_notes` while loading older state with empty defaults.

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_models.py::test_hypothesis_round_trips_generation_trace_and_loads_old_defaults -q
```

Expected before implementation: fail with unexpected `merged_into` / `proximity_notes` keyword or missing attributes.

- [x] **Step 3: Implement metadata defaults**

Add `merged_into: str = ""` and `proximity_notes: list[str] = field(default_factory=list)` to `Hypothesis`, update `from_dict` defaults, and mirror the fields in the TypeScript `Hypothesis` type.

### Task 2: Supervisor Deduplication Workflow

**Files:**
- Modify: `src/code_scientist/supervisor.py`
- Test: `tests/test_supervisor.py`

- [x] **Step 1: Write failing supervisor tests**

Add a direct helper test that applies a `merge_or_contrast_before_ranking` proximity edge and expects the lower-Elo hypothesis to become `merged_duplicate` with `merged_into` set to the representative.

Add a scheduling test that proves `merged_duplicate` hypotheses are excluded from pair scheduling.

Add an integration test that monkeypatches `ProximityAgent.compute_goal_aware` and verifies `run_research_cycle` persists the deduplication status and proximity trace note.

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_supervisor.py::test_apply_proximity_deduplication_marks_duplicate_and_preserves_diversity_notes tests/test_supervisor.py::test_schedule_pairs_skips_merged_duplicate_hypotheses tests/test_supervisor.py::test_supervisor_applies_proximity_deduplication_workflow -q
```

Expected before implementation: fail because helper/status fields do not exist and scheduling still considers every hypothesis.

- [x] **Step 3: Implement minimal workflow**

Add `_apply_proximity_deduplication`, call it after proximity computation in initial and post-evolution proximity stages, and make `_schedule_pairs` ignore `merged_duplicate` hypotheses.

### Task 3: Report And Workbench Visibility

**Files:**
- Modify: `src/code_scientist/reporting.py`
- Modify: `web/src/components/HypothesisDetail.tsx`
- Test: `tests/test_reporting.py`
- Test: `web/src/components/HypothesisDetail.test.ts`

- [x] **Step 1: Write failing rendering tests**

Require ranked hypotheses and HypothesisDetail to display `merged_into` and proximity notes.

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_reporting.py::test_render_report_includes_proximity_deduplication_decisions -q
PATH=/opt/homebrew/bin:$PATH npm test -- HypothesisDetail.test.ts
```

Expected before implementation: fail because report and UI do not render the new fields.

- [x] **Step 3: Implement rendering**

Render merge target and proximity notes in markdown reports and HypothesisDetail.

### Task 4: Verification And Roadmap

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-dedup-workflow.md`

- [x] **Step 1: Update roadmap**

Add slice 117 for proximity dedup workflow and narrow the remaining proximity gap.

- [x] **Step 2: Run verification**

Run focused backend and web tests, full `uv run pytest -q`, full web `npm test`, `npm run build`, `npm run typecheck`, `git diff --check`, and Python compile checks for touched modules.

- [x] **Step 3: Mark plan complete**

Mark checkboxes complete only after matching red/green and final verification evidence exists.
