# Proximity Cluster Bulk Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a scientist apply a merge or preserve-diversity decision to every proximity edge in a cluster from the workbench.

**Architecture:** Reuse the web `RunState` persistence helper to update all existing `proximity_edges` whose `cluster_id` matches the selected cluster, append one auditable `user_feedback` record, and add proximity notes to all hypotheses touched by those edges. Add a small Next route/client wrapper and cluster-level buttons beside the existing derived cluster summary.

**Tech Stack:** TypeScript, Next.js app routes, Mantine buttons, Vitest static render and state-mutator tests.

---

### Task 1: Failing State-Mutation Test

**Files:**
- Modify: `web/src/lib/codeScientist.test.ts`

- [x] **Step 1: Import the desired helper**

```ts
import {
  appendManualHypothesis,
  appendManualReview,
  appendUserFeedback,
  applyProximityClusterOverride,
  applyProximityOverride,
  applyRunCommand,
  buildRunArgs,
  clampInteger,
  listRuns,
  sanitizeRunName,
  updateRunGuidance,
  writeRunControl
} from "./codeScientist";
```

- [x] **Step 2: Add the failing cluster override test**

```ts
it("persists human proximity cluster overrides across matching edges", async ({ task }) => {
  const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
  tempRoot = root;
  process.env.CODE_SCIENTIST_ROOT = root;
  const runDir = path.join(root, "runs", "cluster-loop");
  await mkdir(runDir, { recursive: true });
  const baseState = runState("Cluster loop");
  const editableState = {
    ...baseState,
    hypotheses: [
      ...baseState.hypotheses,
      { ...baseState.hypotheses[0], id: "hyp-2", title: "Second idea" },
      { ...baseState.hypotheses[0], id: "hyp-3", title: "Third idea" }
    ],
    proximity_edges: [
      { source: "hyp-1", target: "hyp-2", similarity: 0.9, method: "embedding_proximity", cluster_id: "cluster-repair" },
      { source: "hyp-2", target: "hyp-3", similarity: 0.82, method: "embedding_proximity", cluster_id: "cluster-repair" },
      { source: "hyp-1", target: "hyp-3", similarity: 0.2, method: "embedding_proximity", cluster_id: "cluster-ui" }
    ]
  };
  await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

  const overrideState = await applyProximityClusterOverride("cluster-loop", {
    clusterId: "cluster-repair",
    decision: "merge",
    reason: "Same repair-loop mechanism."
  });

  const repairEdges = overrideState.proximity_edges?.filter((edge) => edge.cluster_id === "cluster-repair") ?? [];
  expect(repairEdges).toHaveLength(2);
  expect(repairEdges.every((edge) => edge.deduplication_action === "merge_or_contrast_before_ranking")).toBe(true);
  expect(repairEdges.every((edge) => edge.diversity_action === "avoid_redundant_parallel_exploration")).toBe(true);
  expect(overrideState.proximity_edges?.find((edge) => edge.cluster_id === "cluster-ui")?.deduplication_action).toBeUndefined();
  expect(overrideState.user_feedback?.at(-1)).toMatchObject({
    kind: "proximity_cluster_override",
    target_id: "cluster-repair",
    influence: "cluster_management"
  });
  expect(overrideState.hypotheses.every((hypothesis) => hypothesis.proximity_notes?.at(-1)?.includes("Human proximity cluster override"))).toBe(true);
});
```

- [x] **Step 3: Run the focused test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: FAIL because `applyProximityClusterOverride` is not exported.

### Task 2: Failing UI Render Test

**Files:**
- Modify: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Extend the proximity render test**

Pass a no-op cluster override callback:

```ts
onProximityClusterOverride: () => undefined,
```

Add assertions:

```ts
expect(markup).toContain("Merge cluster");
expect(markup).toContain("Preserve cluster");
```

- [x] **Step 2: Run the component test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: FAIL because the cluster action buttons are not rendered.

### Task 3: Implement Cluster Override Plumbing

**Files:**
- Modify: `web/src/lib/codeScientist.ts`
- Modify: `web/src/lib/client.ts`
- Create: `web/src/app/api/runs/[runId]/proximity-cluster/route.ts`
- Modify: `web/src/components/RunInsights.tsx`
- Modify: `web/src/components/Workbench.tsx`

- [x] **Step 1: Add `ProximityClusterOverrideInput` and `applyProximityClusterOverride`**

The helper must:
- validate `clusterId` and decision,
- match edges by `(edge.cluster_id ?? "unclustered") === clusterId`,
- update every matching edge with the chosen merge/preserve controls,
- append `Human cluster override: <reason>` to each matching edge reason when supplied,
- add one `proximity_cluster_override` feedback record,
- add one proximity note to all hypotheses touched by the matching edges,
- throw if no edge matched.

- [x] **Step 2: Add the app route**

Create `web/src/app/api/runs/[runId]/proximity-cluster/route.ts` using the same pattern as the existing proximity route.

- [x] **Step 3: Add the client wrapper**

Add `ProximityClusterOverridePayload` and `submitProximityClusterOverride(runId, payload)` to `web/src/lib/client.ts`.

- [x] **Step 4: Add cluster action props and buttons**

`RunInsights` should accept:

```ts
onProximityClusterOverride?: (clusterId: string, decision: "merge" | "preserve") => void;
```

In the cluster overview, render `Merge cluster` and `Preserve cluster` buttons when the callback is supplied.

- [x] **Step 5: Wire Workbench**

Add `handleProximityClusterOverride` and pass it to `RunInsights`, using the cluster id and a reason that records whether the scientist marked the cluster for merge/deduplication or diversity preservation.

### Task 4: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-cluster-bulk-overrides.md`

- [x] **Step 1: Update the roadmap**

Record slice 122 and narrow the remaining gap from richer multi-edge cluster editing to richer cluster membership editing and interactive graph visualization.

- [x] **Step 2: Run verification**

Run:

```bash
(cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts src/components/RunInsights.test.ts)
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
uv run pytest -q
git diff --check
```

Expected: all commands exit 0.
