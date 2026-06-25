# Proximity Exploration Traces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deterministic proximity edges preserve an inspectable exploration trace instead of only a final reason string.

**Architecture:** Add a backward-compatible `ProximityEdge.exploration_trace` list. Populate lexical and semantic proximity with turn-level traces over lexical overlap, shared evidence, review context, and diversity fallback. Render the trace in reports and the workbench proximity graph.

**Tech Stack:** Python dataclasses, `ProximityAgent`, markdown reporting, Next/Mantine workbench types and rendering, pytest/Vitest.

---

### Task 1: Persist And Populate Proximity Traces

**Files:**
- Modify: `src/code_scientist/models.py`
- Modify: `src/code_scientist/agents.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write failing tests**

Add a model round-trip/default test and a semantic proximity test that expects `exploration_trace` to include lexical/semantic, evidence, review, and assessment turns.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest -q tests/test_models.py::test_match_and_proximity_metadata_round_trip_with_old_state_defaults tests/test_agents.py::test_semantic_proximity_records_exploration_trace`

Expected: FAIL because `ProximityEdge` has no `exploration_trace`.

- [ ] **Step 3: Implement the field and trace population**

Add `exploration_trace` to `ProximityEdge`, default it in `from_dict`, and populate it in `compute()` and `compute_semantic()`.

- [ ] **Step 4: Verify focused tests pass**

Run the same focused pytest command. Expected: PASS.

### Task 2: Render And Verify

**Files:**
- Modify: `src/code_scientist/reporting.py`
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/components/RunInsights.tsx`
- Modify: `tests/test_reporting.py`
- Modify: `web/src/components/RunInsights.test.tsx`
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Add report and UI failing tests**

Assert `render_report()` includes `Proximity trace` and the workbench proximity graph renders trace lines.

- [ ] **Step 2: Implement rendering**

Render `edge.exploration_trace` under proximity graph entries in markdown and the RunInsights proximity panel.

- [ ] **Step 3: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
git diff --check
```

Expected: all commands exit 0.
