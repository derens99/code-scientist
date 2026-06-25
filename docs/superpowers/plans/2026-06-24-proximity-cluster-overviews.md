# Proximity Cluster Overviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make proximity graph inspection cluster-aware by summarizing cluster membership, edge counts, top similarity, and merge/preserve controls in both reports and the workbench Plan tab.

**Architecture:** Derive cluster summaries from existing `ProximityEdge.cluster_id`, source/target ids, similarity, and control fields at render time. Keep raw edge rendering unchanged below the new overview so no persisted schema migration is required.

**Tech Stack:** Python report rendering, TypeScript React static rendering, existing `ProximityEdge` model.

---

### Task 1: Failing Report Test

**Files:**
- Modify: `tests/test_reporting.py`

- [x] **Step 1: Add a report test after the proximity trace tests**

```python
def test_render_report_includes_proximity_cluster_overview(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=1,
        out_dir=tmp_path / "run",
    )
    state = replace(
        state,
        proximity_edges=[
            ProximityEdge(
                source="hyp-a",
                target="hyp-b",
                similarity=0.92,
                method="embedding_proximity",
                cluster_id="cluster-repair",
                deduplication_action="merge_or_contrast_before_ranking",
            ),
            ProximityEdge(
                source="hyp-a",
                target="hyp-c",
                similarity=0.31,
                method="embedding_proximity",
                cluster_id="cluster-repair",
                diversity_action="preserve_as_diversity_candidate",
            ),
        ],
    )

    report = render_report(state)

    assert "### Proximity Cluster Overview" in report
    assert "cluster-repair: 2 edges; 3 hypotheses; top similarity 0.920" in report
    assert "Controls: merge 1; preserve 1" in report
```

- [x] **Step 2: Run the test and confirm RED**

Run: `uv run pytest tests/test_reporting.py::test_render_report_includes_proximity_cluster_overview -q`

Expected: FAIL because the report does not render a cluster overview yet.

### Task 2: Failing Workbench Render Test

**Files:**
- Modify: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Extend the proximity render test**

Add assertions to the existing proximity trace test:

```ts
expect(markup).toContain("Cluster overview");
expect(markup).toContain("cluster-shared");
expect(markup).toContain("1 edge");
expect(markup).toContain("2 hypotheses");
```

- [x] **Step 2: Run the test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: FAIL because the Plan tab does not render cluster summaries yet.

### Task 3: Implement Derived Cluster Summaries

**Files:**
- Modify: `src/code_scientist/reporting.py`
- Modify: `web/src/components/RunInsights.tsx`
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-cluster-overviews.md`

- [x] **Step 1: Add report cluster summary rendering**

In `render_report`, before listing individual proximity edges, render:

```text
### Proximity Cluster Overview

- cluster-repair: 2 edges; 3 hypotheses; top similarity 0.920
  - Controls: merge 1; preserve 1
```

Use a small helper that groups `ProximityEdge` values by `cluster_id or "unclustered"` and sorts by descending top similarity.

- [x] **Step 2: Add Workbench cluster summary rendering**

In `PlanContextPanel`, compute summaries from `proximityEdges` and render them above the edge list with badges/text for edge count, hypothesis count, top similarity, and merge/preserve counts.

- [x] **Step 3: Update the roadmap**

Record slice 121 and narrow the remaining graph gap from only a top-edge list to richer interactive graph visualization beyond derived cluster summaries.

- [x] **Step 4: Run verification**

Run:

```bash
uv run pytest tests/test_reporting.py::test_render_report_includes_proximity_cluster_overview -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts)
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands exit 0.
