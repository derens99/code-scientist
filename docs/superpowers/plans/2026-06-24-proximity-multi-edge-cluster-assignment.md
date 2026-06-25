# Proximity Multi-Edge Cluster Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let command-entry users assign all existing proximity edges among three or more hypotheses to a named cluster in one operation.

**Architecture:** Extend the existing `cluster ... as ...` command parser. Two hypotheses keep the current single-edge path; three or more hypotheses call a new multi-member assignment helper that updates every existing pair edge among the listed members, appends audit feedback, and adds proximity notes to touched hypotheses.

**Tech Stack:** Next.js filesystem-backed run-state helpers, TypeScript, Vitest.

---

### Task 1: Failing Multi-Edge Command Test

**Files:**
- Modify: `web/src/lib/codeScientist.test.ts`

- [x] **Step 1: Add a failing multi-edge assignment test**

Create a state with three hypotheses and multiple existing proximity edges, then run:

```ts
await applyRunCommand("membership-loop", {
  command: "cluster hyp-3 hyp-1 hyp-2 as cluster-human-review"
});
```

Assert every existing edge among `hyp-1`, `hyp-2`, and `hyp-3` gets `cluster_id: "cluster-human-review"`, unrelated edges remain unchanged, and user feedback/proximity notes are written.

- [x] **Step 2: Run focused tests and confirm RED**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: FAIL because the command parser only accepts exactly two hypothesis ids.

### Task 2: Multi-Member Assignment Helper

**Files:**
- Modify: `web/src/lib/codeScientist.ts`

- [x] **Step 1: Add `assignProximityClusterMembers`**

Validate at least two unique hypotheses, confirm all ids exist, update every existing edge whose unordered pair is fully contained by the requested member set, and throw if no edge matched.

- [x] **Step 2: Persist audit metadata**

Append `Human cluster assignment: <cluster-id>.` to every changed edge reason, add one `proximity_cluster_assignment` feedback record, and add one note to every touched hypothesis.

- [x] **Step 3: Extend command parsing**

Parse `cluster hyp-a hyp-b hyp-c as cluster-id` into a multi-member assignment while preserving exact two-hypothesis behavior for the current single-edge command.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run: `cd web && PATH=/opt/homebrew/bin:$PATH npm test -- src/lib/codeScientist.test.ts`

Expected: PASS.

### Task 3: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-proximity-multi-edge-cluster-assignment.md`

- [x] **Step 1: Update the roadmap**

Record slice 128:

```text
128. Add command-backed multi-edge proximity cluster assignment, letting users move every existing edge among three or more named hypotheses into a cluster with feedback and hypothesis-note audit trails.
```

Update implementation status to slices `1-128` and narrow the remaining graph membership wording from multi-edge editing to drag/drop or richer visual graph editing.

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
