# Proximity Graph Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an interactive graph-neighborhood view in the workbench so scientists can inspect proximity cluster membership and adjacent hypotheses from the Plan tab.

**Architecture:** Keep this as a derived frontend view over existing `ProximityEdge` records. `RunInsights` will summarize graph nodes from incident edges, render node degree/cluster/strongest-link context, and expose existing per-edge merge/preserve handlers beside each visible neighbor.

**Tech Stack:** React, Mantine components, existing `ProximityEdge` and `Hypothesis` types, Vitest static markup tests.

---

### Task 1: Failing Graph-View Test

**Files:**
- Modify: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Add a failing proximity graph visualization test**

Add this test inside `describe("RunInsights", ...)`:

```ts
it("renders a graph-neighborhood view for proximity edges", () => {
  const base: Hypothesis = {
    id: "hyp-a",
    title: "Assumption audit",
    claim: "A claim",
    rationale: "A rationale",
    assumptions: [],
    evidence_refs: [],
    test_plan: {
      experiment: "Run a benchmark",
      metrics: ["pass_rate"],
      success_condition: "Improve pass rate"
    },
    risks: [],
    origin: "generation",
    parent_ids: [],
    elo: 1216,
    status: "accepted"
  };
  const hypotheses = [
    base,
    { ...base, id: "hyp-b", title: "Freshness gate" },
    { ...base, id: "hyp-c", title: "Trace replay memory" }
  ];
  const edges: ProximityEdge[] = [
    {
      source: "hyp-a",
      target: "hyp-b",
      similarity: 0.82,
      method: "embedding_proximity",
      cluster_id: "cluster-audit",
      deduplication_action: "merge_or_contrast_before_ranking"
    },
    {
      source: "hyp-a",
      target: "hyp-c",
      similarity: 0.64,
      method: "semantic_evidence_overlap",
      cluster_id: "cluster-replay",
      diversity_action: "preserve_as_diversity_candidate"
    }
  ];

  const markup = renderToStaticMarkup(
    React.createElement(
      MantineProvider,
      {},
      React.createElement(RunInsights, {
        matches: [],
        metaReviews: [],
        hypotheses,
        proximityEdges: edges,
        contextSnapshots: [],
        defaultTab: "plan",
        onProximityOverride: () => undefined,
        report: ""
      })
    )
  );

  expect(markup).toContain("Graph neighborhoods");
  expect(markup).toContain("Assumption audit");
  expect(markup).toContain("Degree 2");
  expect(markup).toContain("Strongest 0.820");
  expect(markup).toContain("Clusters: cluster-audit, cluster-replay");
  expect(markup).toContain("Neighbor: Freshness gate");
  expect(markup).toContain("Neighbor: Trace replay memory");
  expect(markup).toContain("Merge edge");
  expect(markup).toContain("Preserve edge");
});
```

- [x] **Step 2: Run the focused test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: FAIL because the Plan tab currently renders cluster summaries and edge rows, but no `Graph neighborhoods` view.

### Task 2: Derived Graph Rendering

**Files:**
- Modify: `web/src/components/RunInsights.tsx`

- [x] **Step 1: Add graph summary types**

Add these local types near `ProximityClusterSummary`:

```ts
type ProximityGraphNode = {
  id: string;
  title: string;
  degree: number;
  strongestSimilarity: number;
  clusters: string[];
  mergeCount: number;
  preserveCount: number;
  neighbors: ProximityGraphNeighbor[];
};

type ProximityGraphNeighbor = {
  id: string;
  title: string;
  similarity: number;
  clusterId: string;
  method: string;
  edge: ProximityEdge;
};
```

- [x] **Step 2: Derive graph nodes from edges**

Add `summarizeProximityGraph(edges, hypotheses)` near `summarizeProximityClusters`. It must:
- add both endpoints of every proximity edge,
- count node degree from incident edges,
- track the highest incident similarity as `strongestSimilarity`,
- collect sorted cluster ids with `unclustered` for missing `cluster_id`,
- count incident merge and preserve actions,
- sort neighbors by similarity descending, then title,
- sort nodes by degree descending, then strongest similarity descending, then title.

- [x] **Step 3: Render the graph-neighborhood section**

Inside `PlanContextPanel`, compute:

```ts
const graphNodes = summarizeProximityGraph(proximityEdges, hypotheses);
```

Then render a section before `Cluster overview`:

```tsx
{graphNodes.length ? (
  <Stack gap={4}>
    <Text fw={700} size="sm">Graph neighborhoods</Text>
    {graphNodes.slice(0, 6).map((node) => (
      <Paper key={node.id} p="xs" withBorder radius="sm" bg="#fbfcfe">
        ...
      </Paper>
    ))}
  </Stack>
) : null}
```

Each node row must show the title, `Degree N`, `Strongest X.XXX`, `Clusters: ...`, optional merge/preserve incident counts, and each visible neighbor as `Neighbor: <title>` with cluster/method/similarity metadata. When `onProximityOverride` is provided, each neighbor row must expose `Merge edge` and `Preserve edge` buttons that call `onProximityOverride(neighbor.edge, "merge")` or `"preserve"`.

- [x] **Step 4: Run the focused test and confirm GREEN**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: PASS.

### Task 3: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-graph-visualization.md`

- [x] **Step 1: Update the roadmap**

Record slice 124:

```text
124. Add an interactive proximity graph-neighborhood view in the workbench Plan tab, deriving node degree, cluster memberships, strongest links, neighbors, and per-edge merge/preserve controls from existing `ProximityEdge` records.
```

Also update the implementation status from slices `1-123` to `1-124`, mention the graph-neighborhood view, and narrow remaining proximity wording from `interactive proximity graph visualization` to richer layout/graph manipulation beyond the graph-neighborhood view.

- [x] **Step 2: Run verification**

Run:

```bash
(cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts)
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
uv run pytest -q
git diff --check
```

Expected: all commands exit 0.
