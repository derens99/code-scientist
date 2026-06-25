# Human Editable Proximity Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a scientist override computed proximity decisions for an existing edge by marking it as a merge/deduplication candidate or preserving it as a diversity candidate.

**Architecture:** Reuse the existing web `RunState` persistence helper to update `proximity_edges`, append auditable `user_feedback`, and add visible proximity notes to affected hypotheses. Add a Next route and client wrapper, then surface compact action buttons in the existing Plan tab proximity graph.

**Tech Stack:** Next.js app routes, TypeScript, Mantine buttons, Vitest static render tests, JSON persisted `RunState`.

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
  applyProximityOverride,
  applyRunCommand,
  buildRunArgs,
  listRuns,
  sanitizeRunName,
  startRun,
  updateRunGuidance,
  writeRunControl
} from "./codeScientist";
```

- [x] **Step 2: Add a failing test**

```ts
const editableState = runState("Human loop");
editableState.hypotheses.push({
  ...editableState.hypotheses[0],
  id: "hyp-2",
  title: "Diverse idea"
});
editableState.proximity_edges = [
  {
    source: "hyp-1",
    target: "hyp-2",
    similarity: 0.86,
    method: "embedding_proximity",
    reason: "Computed as close neighbors."
  }
];
await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

const overrideState = await applyProximityOverride("human-loop", {
  source: "hyp-2",
  target: "hyp-1",
  decision: "preserve",
  clusterId: "cluster-human-review",
  reason: "Different benchmark failure mode."
});

expect(overrideState.proximity_edges?.[0]).toMatchObject({
  source: "hyp-1",
  target: "hyp-2",
  cluster_id: "cluster-human-review",
  diversity_action: "preserve_as_diversity_candidate",
  reason: "Computed as close neighbors. Human override: Different benchmark failure mode."
});
expect(overrideState.user_feedback?.at(-1)).toMatchObject({
  kind: "proximity_override",
  target_id: "hyp-1:hyp-2",
  influence: "cluster_management"
});
expect(overrideState.hypotheses[0].proximity_notes?.at(-1)).toContain("Human proximity override");
```

- [x] **Step 3: Run the test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: FAIL because `applyProximityOverride` is not exported.

### Task 2: State Helper, Route, and Client

**Files:**
- Modify: `web/src/lib/codeScientist.ts`
- Modify: `web/src/lib/client.ts`
- Create: `web/src/app/api/runs/[runId]/proximity/route.ts`

- [x] **Step 1: Add the input type and helper**

```ts
export type ProximityOverrideInput = {
  source: string;
  target: string;
  decision: "merge" | "preserve";
  clusterId?: string;
  reason?: string;
};
```

The helper must:
- validate both hypothesis ids are present,
- find the proximity edge regardless of source/target order,
- set `deduplication_action` to `merge_or_contrast_before_ranking` and `diversity_action` to `avoid_redundant_parallel_exploration` for `merge`,
- set `deduplication_action` to `undefined` and `diversity_action` to `preserve_as_diversity_candidate` for `preserve`,
- append `Human override: <reason>` to the edge reason when a reason is supplied,
- add a `proximity_override` feedback record with `influence: "cluster_management"`,
- append a note to both affected hypotheses.

- [x] **Step 2: Add a route**

Create `web/src/app/api/runs/[runId]/proximity/route.ts` with the same pattern as `feedback/route.ts`, calling `applyProximityOverride`.

- [x] **Step 3: Add the client wrapper**

Add `ProximityOverridePayload` and `submitProximityOverride(runId, payload)` to `web/src/lib/client.ts`, using the existing `postRunInput` helper with segment `"proximity"`.

- [x] **Step 4: Run the focused state test and confirm GREEN**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: PASS.

### Task 3: Workbench Controls and Documentation

**Files:**
- Modify: `web/src/components/RunInsights.tsx`
- Modify: `web/src/components/RunInsights.test.ts`
- Modify: `web/src/components/Workbench.tsx`
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-human-editable-proximity-controls.md`

- [x] **Step 1: Add UI callback props**

`RunInsights` should accept:

```ts
onProximityOverride?: (edge: ProximityEdge, decision: "merge" | "preserve") => void;
proximityOverrideLoading?: boolean;
```

`PlanContextPanel` should render compact action buttons for each edge when `onProximityOverride` is supplied.

- [x] **Step 2: Wire Workbench to the client helper**

`Workbench` should call `submitProximityOverride` with the selected run id, update local `state`, and show errors through the existing error alert.

- [x] **Step 3: Add static render coverage**

Extend the proximity trace test to pass a no-op `onProximityOverride` and assert the rendered markup contains `Merge` and `Preserve`.

- [x] **Step 4: Update the roadmap**

Record slice 120 and narrow the proximity remaining gap from human-editable cluster management to richer multi-edge cluster editing and visualization.

- [x] **Step 5: Run verification**

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
