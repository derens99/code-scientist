# Proximity Graph Membership Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let workbench users reassign a proximity edge to a named cluster directly from the graph-neighborhood view.

**Architecture:** Reuse the existing command-backed cluster assignment behavior from `applyRunCommand` instead of adding a second mutation helper. `RunInsights` will expose a graph-neighbor cluster input and `Assign cluster` action, while `Workbench` will translate that action into `cluster <source> <target> as <cluster-id>` through `submitRunCommand`.

**Tech Stack:** React, Mantine `TextInput` and `Button`, existing `ProximityEdge` type, existing `submitRunCommand` client helper, Vitest static markup tests.

---

### Task 1: Failing Graph Membership Test

**Files:**
- Modify: `web/src/components/RunInsights.test.ts`

- [x] **Step 1: Add a failing membership-control render test**

Extend the existing `"renders a graph-neighborhood view for proximity edges"` test with:

```ts
expect(markup).toContain("Cluster id");
expect(markup).toContain("Assign cluster");
```

- [x] **Step 2: Run the focused test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: FAIL because graph neighbor rows expose merge/preserve actions but no cluster assignment input or action.

### Task 2: Graph Assignment UI

**Files:**
- Modify: `web/src/components/RunInsights.tsx`

- [x] **Step 1: Add the assignment prop**

Extend props for `RunInsights` and `PlanContextPanel`:

```ts
onProximityClusterAssignment?: (edge: ProximityEdge, clusterId: string) => void;
```

Pass it through from `RunInsights` into `PlanContextPanel`.

- [x] **Step 2: Add controlled cluster drafts**

Inside `PlanContextPanel`, add:

```ts
const [clusterDrafts, setClusterDrafts] = useState<Record<string, string>>({});
```

Use a stable edge key helper so each graph neighbor input keeps its own draft cluster id.

- [x] **Step 3: Render cluster assignment controls**

For each graph neighbor row, render:

```tsx
<TextInput
  size="xs"
  aria-label={`Cluster id for ${node.title} and ${neighbor.title}`}
  placeholder="Cluster id"
  value={draftValue}
  onChange={(event) => setClusterDrafts({ ...clusterDrafts, [edgeKey]: event.currentTarget.value })} />
<Button size="xs" onClick={() => onProximityClusterAssignment(neighbor.edge, draftValue.trim())}>
  Assign cluster
</Button>
```

The button must be disabled when no trimmed cluster id is present. Keep existing merge/preserve buttons unchanged.

- [x] **Step 4: Run the focused test and confirm GREEN**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/components/RunInsights.test.ts`

Expected: PASS.

### Task 3: Workbench Wiring

**Files:**
- Modify: `web/src/components/Workbench.tsx`

- [x] **Step 1: Add the handler**

Add:

```ts
async function handleProximityClusterAssignment(edge: ProximityEdge, clusterId: string) {
  if (!selectedRunId || !clusterId.trim()) {
    return;
  }
  await saveHumanInput(() =>
    submitRunCommand(selectedRunId, {
      command: `cluster ${edge.source} ${edge.target} as ${clusterId.trim()}`
    })
  );
}
```

- [x] **Step 2: Pass the handler to `RunInsights`**

Add `onProximityClusterAssignment={handleProximityClusterAssignment}` to the selected-run `RunInsights` props.

- [x] **Step 3: Run web tests**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test`

Expected: PASS.

### Task 4: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-graph-membership-controls.md`

- [x] **Step 1: Update the roadmap**

Record slice 125:

```text
125. Add graph-neighborhood cluster membership controls in the workbench, letting users assign an existing proximity edge to a typed cluster id through the command-backed assignment path.
```

Update implementation status to slices `1-125`, mention graph-neighborhood cluster assignment controls, and narrow remaining proximity wording from `interactive graph membership editing` to broader drag/drop or multi-edge graph membership editing.

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
