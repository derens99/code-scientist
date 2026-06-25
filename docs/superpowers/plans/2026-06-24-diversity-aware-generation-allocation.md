# Diversity-Aware Generation Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allocate generation budget across active proposal methods using current origin coverage and proximity-cluster saturation, instead of splitting every cycle only by remaining method count.

**Architecture:** Add a deterministic supervisor helper that scores each active generation method from existing hypotheses and proximity edges, favoring underrepresented or less-cluster-saturated methods. The generation task payload will record the selected allocation, and `_generate_for_plan` will consume the same allocation so task state, traces, and behavior agree.

**Tech Stack:** Python supervisor orchestration, existing `Hypothesis` and `ProximityEdge` models, pytest.

---

### Task 1: Failing Allocation Tests

**Files:**
- Modify: `tests/test_supervisor.py`

- [x] **Step 1: Add a failing underrepresentation test**

Add a test that builds accepted hypotheses from two generation methods plus proximity edges showing cluster saturation, then asserts the allocation helper places the uncovered active method first and records an underrepresented-method reason.

- [x] **Step 2: Add a failing task-payload test**

Extend the state-writing test to assert the completed generation task payload contains `generation_allocations` entries with `mode`, `limit`, and `reason`.

- [x] **Step 3: Run focused tests and confirm RED**

Run: `uv run pytest tests/test_supervisor.py -q`

Expected: FAIL because no allocation helper or payload field exists yet.

### Task 2: Supervisor Allocation Helper

**Files:**
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Add method attribution helpers**

Add helpers that map a hypothesis `origin` back to an active generation method where possible, including deterministic origins like `generation`, `generation:<mode>`, and LLM origins like `anthropic-haiku:<mode>`.

- [x] **Step 2: Add `_allocate_generation_methods`**

Score active modes by active hypothesis count, merged-duplicate count, incident proximity-cluster count, and duplicate-control count. Sort lower saturation first, allocate the requested budget deterministically, and return payload-safe dictionaries:

```python
{"mode": mode, "limit": mode_limit, "reason": "..."}
```

- [x] **Step 3: Run focused tests and confirm helper behavior**

Run: `uv run pytest tests/test_supervisor.py -q`

Expected: the helper test passes; task-payload assertion may still fail until the generation flow is wired.

### Task 3: Generation Flow Wiring

**Files:**
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Compute allocations before creating the generate task**

Use `_allocate_generation_methods(active_generation_methods, generation_limit, hypotheses, proximity_edges)` when the cycle computes `generation_limit`.

- [x] **Step 2: Persist allocation metadata**

Add `generation_allocations` to the generate task payload.

- [x] **Step 3: Consume the allocation in `_generate_for_plan`**

Extend `_generate_for_plan` to accept optional `generation_allocations`, `existing_hypotheses`, and `proximity_edges`; loop over allocation entries instead of the old even split.

- [x] **Step 4: Add trace notes**

Include each mode allocation reason in the generation trace notes for auditability.

- [x] **Step 5: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/test_supervisor.py -q`

Expected: PASS.

### Task 4: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-diversity-aware-generation-allocation.md`

- [x] **Step 1: Update the roadmap**

Record slice 126:

```text
126. Add diversity-aware generation allocation that uses current origin coverage and proximity-cluster saturation to prioritize underrepresented proposal methods, persists the allocation in task payloads, and traces the allocation reason per generation mode.
```

Update implementation status to slices `1-126` and narrow remaining resource-allocation wording to broader asynchronous or production-resource allocation beyond method-level generation allocation and evolution leader selection.

- [x] **Step 2: Run verification**

Run:

```bash
uv run pytest tests/test_supervisor.py -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands exit 0.
