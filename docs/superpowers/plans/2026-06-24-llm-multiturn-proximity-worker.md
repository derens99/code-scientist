# LLM Multi-Turn Proximity Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider-backed goal-aware proximity behave more like the paper's exploratory proximity worker instead of a single schema call.

**Architecture:** Keep deterministic lexical/semantic proximity unchanged. When `ProximityAgent` has an LLM client, run three focused LLM turns for semantic neighborhood mapping, evidence/review overlap analysis, and final clustering synthesis; parse the final turn with the existing edge schema and persist the turn summaries in each edge's `exploration_trace`.

**Tech Stack:** Python dataclasses, existing LLM client interface, pytest, `uv`.

---

### Task 1: LLM Proximity Uses Multiple Exploration Turns

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing multi-turn proximity test**

Add `test_llm_proximity_uses_multi_turn_exploration_trace` to `tests/test_agents.py`.

Use a fake LLM that records prompts and returns:

```python
if "proximity turn 1 semantic neighborhood mapping" in lowered:
    return "Neighborhood map: hyp-left and hyp-right both target benchmark-seeded repair loops."
if "proximity turn 2 evidence and review overlap" in lowered:
    return "Overlap analysis: both candidates cite ev-shared and have accepting reviews."
if "proximity turn 3 clustering synthesis" in lowered:
    return json.dumps({
        "edges": [
            {
                "source": "hyp-left",
                "target": "hyp-right",
                "similarity": 0.86,
                "reason": "Both proposals share benchmark evidence and repair-loop review context.",
                "cluster_id": "benchmark-repair",
                "evidence_refs": ["ev-shared"],
                "review_refs": ["rev-left", "rev-right"],
            }
        ]
    })
```

Assert:

```python
assert len(fake_llm.calls) == 3
assert edges[0].method == "llm_goal_aware_proximity"
assert any("LLM turn 1 semantic neighborhood mapping" in line for line in edges[0].exploration_trace)
assert any("LLM turn 2 evidence and review overlap" in line for line in edges[0].exploration_trace)
assert any("LLM turn 3 clustering synthesis" in line for line in edges[0].exploration_trace)
assert edges[0].exploration_trace[-1].startswith("LLM multi-turn proximity assessment:")
```

- [x] **Step 2: Run the proximity test to verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_proximity_uses_multi_turn_exploration_trace -q
```

Expected: FAIL because `_compute_goal_aware_with_llm()` currently makes one generic proximity call.

- [x] **Step 3: Implement LLM multi-turn proximity**

In `_compute_goal_aware_with_llm`, replace the single prompt call with:

- `Proximity turn 1 semantic neighborhood mapping`;
- `Proximity turn 2 evidence and review overlap`;
- `Proximity turn 3 clustering synthesis`.

Parse the third response with the existing edge parser. Append compact lines:

```python
LLM turn 1 semantic neighborhood mapping: ...
LLM turn 2 evidence and review overlap: ...
LLM turn 3 clustering synthesis: ...
LLM multi-turn proximity assessment: ...
```

to every parsed edge's `exploration_trace`, preserving any trace lines supplied in the JSON.

- [x] **Step 4: Run focused proximity tests to verify green**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_proximity_uses_multi_turn_exploration_trace tests/test_agents.py::test_proximity_can_use_llm_goal_aware_schema -q
```

Expected: PASS. Update the existing fake LLM in `test_proximity_can_use_llm_goal_aware_schema` if needed so it accepts the new turn prompts while still proving provider-backed schema parsing.

### Task 2: Supervisor Provider Smoke Covers Multi-Turn Proximity

**Files:**
- Modify: `tests/test_supervisor.py`

- [x] **Step 1: Update the provider smoke fake**

In `test_supervisor_anthropic_provider_drives_plan_and_all_agent_roles`, add handlers for:

```python
if "proximity turn 1 semantic neighborhood mapping" in lowered:
    return "Neighborhood map: benchmark-grounded candidates should cluster."
if "proximity turn 2 evidence and review overlap" in lowered:
    return "Overlap analysis: shared validation caveats connect the candidates."
if "proximity turn 3 clustering synthesis" in lowered:
    return json.dumps({... existing edge JSON ...})
```

- [x] **Step 2: Run the provider smoke test**

Run:

```bash
uv run pytest tests/test_supervisor.py::test_supervisor_anthropic_provider_drives_plan_and_all_agent_roles -q
```

Expected: PASS, with proximity still producing `llm_goal_aware_proximity` edges.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-llm-multiturn-proximity-worker.md`

- [x] **Step 1: Update roadmap**

Add slice 115:

```markdown
115. Add provider-backed multi-turn proximity exploration, with auditable semantic-neighborhood, evidence/review-overlap, and clustering-synthesis traces.
```

Update implementation-status wording from slices `1-114` to `1-115` and narrow the remaining proximity gap accordingly.

- [x] **Step 2: Full verification**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_proximity_uses_multi_turn_exploration_trace tests/test_agents.py::test_proximity_can_use_llm_goal_aware_schema tests/test_supervisor.py::test_supervisor_anthropic_provider_drives_plan_and_all_agent_roles -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
uv run python -m py_compile src/code_scientist/agents.py
```

Expected: all commands pass.

- [x] **Step 3: Mark plan complete**

Mark checkboxes complete only after the corresponding red, green, roadmap, and full verification steps have passed.
