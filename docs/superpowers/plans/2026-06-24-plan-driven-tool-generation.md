# Plan-Driven Tool Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make research plans that allow tool use automatically activate tool-augmented generation when grounded evidence is available.

**Architecture:** Keep `tool_augmented_generation` as the deterministic generation mode added in the previous slice. Extend supervisor method selection so `ResearchPlanConfig.allowed_tools` can add `tool_augmented_generation` to the active generation modes, similar to how grounded evidence currently adds `literature_grounded_generation`. This keeps the paper-aligned behavior plan-driven without changing the CLI, evidence collection, or model interfaces.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Supervisor Method Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing test**

Add `test_supervisor_adds_tool_augmented_generation_when_plan_allows_tools`:

```python
def test_supervisor_adds_tool_augmented_generation_when_plan_allows_tools(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agent.py").write_text(
        "Improve LLM coding agents by mining failed patch recovery traces for assumption audits.\n",
        encoding="utf-8",
    )
    objective = "Improve LLM coding agents"
    goal = ResearchGoal.from_objective(objective)
    plan = replace(
        ResearchPlanConfig.from_goal(goal),
        generation_methods=["paper_seeded_idea_generation"],
        allowed_tools=["repo_search"],
    )

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=4,
        max_matches=1,
        out_dir=tmp_path / "run",
        repo_search_paths=[repo],
        plan_config=plan,
    )

    assert any(
        item.origin == "generation:tool_augmented_generation"
        for item in state.hypotheses
    )
    assert any(trace.action == "tool_augmented_generation" for trace in state.agent_traces)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_adds_tool_augmented_generation_when_plan_allows_tools`

Expected: FAIL because `_active_generation_methods()` currently appends only `literature_grounded_generation`, not `tool_augmented_generation`.

- [x] **Step 3: Implement minimal method selection**

Update `_active_generation_methods(plan, use_grounded)` so it appends `tool_augmented_generation` when:

- grounded/tool evidence is active (`use_grounded` is true),
- `tool_augmented_generation` is not already present,
- `plan.allowed_tools` contains a tool signal other than `deterministic_agents`, such as `repo_search`, `web_search`, `web_evidence`, `openalex_literature_search`, or `literature_search`.

- [x] **Step 4: Verify focused test passes**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_adds_tool_augmented_generation_when_plan_allows_tools`

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-tool-generation.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 95. Update Phase 3 status to say supervisor generation mode selection now activates tool-augmented generation from `allowed_tools` when grounded/tool evidence is present.

- [x] **Step 2: Mark this plan complete**

Replace task checkboxes with `[x]` after the implementation and verification steps finish.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-tool-generation.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
