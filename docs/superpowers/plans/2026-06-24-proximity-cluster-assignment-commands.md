# Proximity Cluster Assignment Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a scientist move an existing proximity edge into a named cluster through the workbench command-entry path without changing merge or preserve-diversity controls.

**Architecture:** Add a web state helper that finds an existing proximity edge by hypothesis pair, updates only `cluster_id` and audit text, appends `proximity_cluster_assignment` feedback, and adds proximity notes to the affected hypotheses. Extend `applyRunCommand` to parse `cluster hyp-a hyp-b as cluster-name` commands and call the helper.

**Tech Stack:** TypeScript state mutation helper, existing Next command route, Vitest.

---

### Task 1: Failing Command-State Test

**Files:**
- Modify: `web/src/lib/codeScientist.test.ts`

- [x] **Step 1: Add a failing command test**

```ts
it("assigns an existing proximity edge to a named cluster from a command", async ({ task }) => {
  const root = await mkdtemp(path.join(os.tmpdir(), `${task.id}-`));
  tempRoot = root;
  process.env.CODE_SCIENTIST_ROOT = root;
  const runDir = path.join(root, "runs", "membership-loop");
  await mkdir(runDir, { recursive: true });
  const baseState = runState("Membership loop");
  const editableState = {
    ...baseState,
    hypotheses: [
      ...baseState.hypotheses,
      { ...baseState.hypotheses[0], id: "hyp-2", title: "Second idea" }
    ],
    proximity_edges: [
      {
        source: "hyp-1",
        target: "hyp-2",
        similarity: 0.77,
        method: "embedding_proximity",
        reason: "Computed neighborhood."
      }
    ]
  };
  await writeFile(path.join(runDir, "state.json"), JSON.stringify(editableState), "utf8");

  const commandState = await applyRunCommand("membership-loop", {
    command: "cluster hyp-2 hyp-1 as cluster-human-review"
  });

  expect(commandState.proximity_edges?.[0]).toMatchObject({
    source: "hyp-1",
    target: "hyp-2",
    cluster_id: "cluster-human-review",
    reason: "Computed neighborhood. Human cluster assignment: cluster-human-review."
  });
  expect(commandState.proximity_edges?.[0].deduplication_action).toBeUndefined();
  expect(commandState.proximity_edges?.[0].diversity_action).toBeUndefined();
  expect(commandState.user_feedback?.at(-1)).toMatchObject({
    kind: "proximity_cluster_assignment",
    target_id: "hyp-1:hyp-2",
    influence: "cluster_management"
  });
  expect(commandState.hypotheses[0].proximity_notes?.at(-1)).toContain("Human proximity cluster assignment");
  expect(commandState.hypotheses[1].proximity_notes?.at(-1)).toContain("Human proximity cluster assignment");
});
```

- [x] **Step 2: Run the focused test and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: FAIL because the command currently becomes a generic `command_note`.

### Task 2: Minimal Implementation

**Files:**
- Modify: `web/src/lib/codeScientist.ts`

- [x] **Step 1: Add `assignProximityEdgeCluster`**

The helper must:
- validate source, target, and cluster id,
- find the existing edge regardless of source/target order,
- update only `cluster_id` and append a `Human cluster assignment: <cluster>.` reason suffix,
- preserve existing `deduplication_action` and `diversity_action`,
- append `proximity_cluster_assignment` feedback,
- add proximity notes to the two affected hypotheses,
- throw when the edge is missing.

- [x] **Step 2: Parse cluster assignment commands**

In `applyRunCommand`, parse:

```text
cluster hyp-2 hyp-1 as cluster-human-review
cluster hyp-2 hyp-1 into cluster-human-review
cluster hyp-2 hyp-1 to cluster-human-review
```

and route them to `assignProximityEdgeCluster`.

- [x] **Step 3: Run the focused test and confirm GREEN**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: PASS.

### Task 3: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-cluster-assignment-commands.md`

- [x] **Step 1: Update the roadmap**

Record slice 123 and narrow the remaining gap from richer cluster membership editing to interactive graph membership editing beyond command-based edge assignment.

- [x] **Step 2: Run verification**

Run:

```bash
(cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts)
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
uv run pytest -q
git diff --check
```

Expected: all commands exit 0.
