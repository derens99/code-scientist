# Proximity Merged Hypothesis Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make proximity deduplication synthesize representative hypotheses by folding useful evidence, assumptions, risks, rationale context, and trace notes from merged duplicates into the kept representative.

**Architecture:** Extend the existing `_apply_proximity_deduplication` path instead of creating a new clustering subsystem. When a duplicate is merged into a representative, synthesize the representative with bounded unions of evidence refs, assumptions, and risks; append a concise rationale sentence and generation trace entry; then keep the existing duplicate status/merge note behavior.

**Tech Stack:** Python dataclasses, pytest, markdown roadmap documentation.

---

### Task 1: Representative Synthesis Test

**Files:**
- Modify: `tests/test_supervisor.py`

- [x] **Step 1: Write failing helper test**

Add a test requiring `_apply_proximity_deduplication` to fold duplicate content into the representative:

```python
assert by_id[representative.id].evidence_refs == ["ev-keeper", "ev-duplicate"]
assert "duplicate assumption" in by_id[representative.id].assumptions
assert "duplicate risk" in by_id[representative.id].risks
assert "Proximity synthesis from hyp-duplicate" in by_id[representative.id].rationale
assert any("Proximity synthesis:" in line for line in by_id[representative.id].generation_trace)
```

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_supervisor.py::test_apply_proximity_deduplication_synthesizes_representative_content -q
```

Expected before implementation: fail because representative fields are unchanged.

### Task 2: Synthesis Implementation

**Files:**
- Modify: `src/code_scientist/supervisor.py`
- Test: `tests/test_supervisor.py`

- [x] **Step 1: Implement synthesis helper**

Add helper logic that replaces the kept representative with synthesized evidence refs, assumptions, risks, rationale, and generation trace before adding the existing proximity note.

- [x] **Step 2: Verify focused green**

Run:

```bash
uv run pytest tests/test_supervisor.py::test_apply_proximity_deduplication_synthesizes_representative_content tests/test_supervisor.py::test_apply_proximity_deduplication_marks_duplicate_and_preserves_diversity_notes tests/test_supervisor.py::test_apply_proximity_deduplication_keeps_two_active_representatives -q
```

Expected: all pass.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-merged-hypothesis-synthesis.md`

- [x] **Step 1: Update roadmap**

Add slice 118 and narrow the remaining proximity gap from "synthesized merged hypotheses" to richer human-editable cluster management and diversity allocation.

- [x] **Step 2: Run verification**

Run focused tests, full `uv run pytest -q`, web `npm test`, web `npm run build`, web `npm run typecheck`, `git diff --check`, and Python compile checks for touched modules.

- [x] **Step 3: Mark plan complete**

Mark all checkboxes only after matching verification evidence exists.
