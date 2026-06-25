# Embedding Proximity Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add embedding-backed proximity edges with explicit deduplication and diversity controls that are persisted, scheduled against, and visible in reports and the workbench.

**Architecture:** Reuse the existing deterministic local embedding substrate in `EvidenceStore` for pairwise hypothesis similarity. Extend `ProximityEdge` with backwards-compatible control fields, make grounded fallback proximity use embedding edges, and feed the controls into ranking-pair and task-priority scoring. Render the controls in the markdown report and RunInsights proximity panel.

**Tech Stack:** Python dataclasses, pytest, local hashed char-ngram embeddings, Next.js/React, Vitest.

---

### Task 1: Edge Schema And Embedding API

**Files:**
- Modify: `src/code_scientist/evidence.py`
- Modify: `src/code_scientist/models.py`
- Test: `tests/test_evidence.py`
- Test: `tests/test_models.py`

- [x] **Step 1: Write failing tests**

Added:

```python
def test_evidence_store_exposes_local_embedding_similarity_for_proximity():
    related = EvidenceStore.local_embedding_similarity(
        "benchmark seeded repair loop",
        "benchmark-seeded repair loops",
    )
    unrelated = EvidenceStore.local_embedding_similarity(
        "benchmark seeded repair loop",
        "ui layout density scan speed",
    )

    assert related > 0.9
    assert unrelated < related
```

Extended proximity edge round-trip coverage to require:

```python
assert restored_edge.deduplication_action == "merge_or_contrast_before_ranking"
assert restored_edge.diversity_action == "avoid_redundant_parallel_exploration"
assert restored_old_edge.deduplication_action == ""
assert restored_old_edge.diversity_action == ""
```

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_evidence.py::test_evidence_store_exposes_local_embedding_similarity_for_proximity tests/test_models.py::test_match_and_proximity_metadata_round_trip_with_old_state_defaults -q
```

Expected before implementation: fail with missing `EvidenceStore.local_embedding_similarity` and missing `ProximityEdge` control fields.

- [x] **Step 3: Implement schema and API**

Implemented `EvidenceStore.local_embedding_similarity(left, right)` and added backwards-compatible `deduplication_action` / `diversity_action` fields on `ProximityEdge`.

### Task 2: Embedding Proximity Worker And Active Scheduling

**Files:**
- Modify: `src/code_scientist/agents.py`
- Modify: `src/code_scientist/supervisor.py`
- Test: `tests/test_agents.py`
- Test: `tests/test_supervisor.py`

- [x] **Step 1: Write failing proximity tests**

Added direct agent coverage requiring `compute_goal_aware` to produce `embedding_proximity` edges with shared evidence refs, review refs, trace lines, and control actions when an `EvidenceStore` is available.

Added supervisor coverage requiring grounded runs to persist embedding proximity controls.

Added scheduler coverage requiring an embedding deduplication control to outrank a higher raw lexical similarity edge.

- [x] **Step 2: Verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_goal_aware_proximity_uses_embedding_similarity_and_control_actions tests/test_supervisor.py::test_schedule_pairs_prioritizes_embedding_deduplication_controls tests/test_supervisor.py::test_supervisor_records_embedding_proximity_controls_for_grounded_runs -q
```

Expected before implementation: fail because grounded proximity still falls back to `semantic_evidence_overlap` and scheduler ignores control fields.

- [x] **Step 3: Implement worker and scheduler scoring**

Implemented `ProximityAgent.compute_embedding`, routed evidence-backed non-LLM proximity through it, preserved optional provider-supplied control fields, and added embedding/dedup/diversity bonuses to pair scheduling and cluster priority scoring.

### Task 3: Report And Workbench Rendering

**Files:**
- Modify: `src/code_scientist/reporting.py`
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/components/RunInsights.tsx`
- Test: `tests/test_reporting.py`
- Test: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Write failing rendering tests**

Extended report and RunInsights tests to require:

```text
Deduplication control: merge_or_contrast_before_ranking
Diversity control: avoid_redundant_parallel_exploration
Deduplication: merge_or_contrast_before_ranking
Diversity: avoid_redundant_parallel_exploration
```

- [x] **Step 2: Implement rendering**

Rendered control fields in markdown reports and the proximity graph panel, and added the fields to the TypeScript `ProximityEdge` type.

### Task 4: Focused Verification

**Files:**
- Verify: Python focused tests
- Verify: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Run focused backend tests**

Run:

```bash
uv run pytest tests/test_evidence.py::test_evidence_store_exposes_local_embedding_similarity_for_proximity tests/test_models.py::test_match_and_proximity_metadata_round_trip_with_old_state_defaults tests/test_agents.py::test_goal_aware_proximity_uses_embedding_similarity_and_control_actions tests/test_supervisor.py::test_schedule_pairs_prioritizes_embedding_deduplication_controls tests/test_supervisor.py::test_supervisor_records_embedding_proximity_controls_for_grounded_runs tests/test_reporting.py::test_render_report_includes_proximity_exploration_trace -q
```

Observed: `6 passed`.

- [x] **Step 2: Run focused web test**

Run:

```bash
PATH=/opt/homebrew/bin:$PATH npm test -- RunInsights.test.ts
```

Observed: `1 passed` test file, `6 passed` tests.
