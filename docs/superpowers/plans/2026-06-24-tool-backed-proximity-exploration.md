# Tool-Backed Proximity Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make grounded proximity explicitly inspect tool/search evidence for a hypothesis pair and persist that as proximity method, reason, evidence refs, and exploration trace metadata.

**Architecture:** Extend `ProximityAgent.compute_goal_aware`'s evidence-backed fallback so `compute_embedding` can receive the research goal, retrieve pair-level tool evidence from `EvidenceStore`, and upgrade matching edges from generic `embedding_proximity` to `tool_backed_proximity` when tool/search observations support the relation.

**Tech Stack:** Python `ProximityAgent`, `EvidenceStore`, existing `Evidence`, `Hypothesis`, `Review`, and `ProximityEdge` models, pytest.

---

### Task 1: Failing Tool-Backed Proximity Test

**Files:**
- Modify: `tests/test_agents.py`

- [x] **Step 1: Add a tool-backed proximity test**

Create two related hypotheses, one unrelated hypothesis, and a `tool_result_repo_search` evidence item describing the shared repair-loop mechanism. Assert the top edge:

```python
assert top.method == "tool_backed_proximity"
assert "ev-tool-repair" in top.evidence_refs
assert "Tool-backed proximity evidence" in top.reason
assert any("Turn 4 tool evidence exploration" in line for line in top.exploration_trace)
```

- [x] **Step 2: Run focused tests and confirm RED**

Run: `uv run pytest tests/test_agents.py -q`

Expected: FAIL because evidence-backed proximity currently records generic embedding proximity and has no dedicated tool-evidence exploration turn.

### Task 2: Pair-Level Tool Evidence Retrieval

**Files:**
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Pass the goal into embedding proximity**

Change the evidence-backed fallback to call `compute_embedding(goal, hypotheses, reviews, evidence_store)`.

- [x] **Step 2: Select pair-level tool evidence**

Add a helper that builds a pair query from the goal and both hypotheses, retrieves ranked evidence, filters `_is_tool_evidence`, and returns stable evidence refs.

- [x] **Step 3: Upgrade matching edges**

When pair tool refs exist, add them to `evidence_refs`, change the edge method to `tool_backed_proximity`, add a reason part naming the tool refs, add a `Turn 4 tool evidence exploration` trace line, and include the tool refs in the cluster basis.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/test_agents.py -q`

Expected: PASS.

### Task 3: Roadmap and Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-tool-backed-proximity-exploration.md`

- [x] **Step 1: Update the roadmap**

Record slice 127:

```text
127. Add tool-backed proximity exploration, upgrading grounded proximity edges when pair-level tool/search evidence supports a relation and persisting tool refs, method metadata, reasons, and a dedicated exploration trace turn.
```

Update implementation status to slices `1-127` and narrow remaining proximity wording from true tool-backed proximity exploration to broader live tool-follow-up and external tool exploration.

- [x] **Step 2: Run verification**

Run:

```bash
uv run pytest tests/test_agents.py -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands exit 0.
