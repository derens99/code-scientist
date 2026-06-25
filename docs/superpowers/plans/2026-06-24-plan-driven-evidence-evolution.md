# Plan-Driven Evidence Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make research plans with external tool evidence prefer evidence-grounded evolution instead of starting with generic simplification.

**Architecture:** Reuse the existing `evidence_grounding` evolution strategy and its retrieval trace. Extend supervisor strategy selection so grounded runs whose `ResearchPlanConfig.allowed_tools` names external tools pull `evidence_grounding` to the front of the strategy rotation when the plan has not already selected it for the current cycle. This keeps evolution plan-driven and evidence-backed without adding another strategy implementation.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Strategy Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing test**

Add `test_supervisor_prefers_evidence_grounding_evolution_when_plan_allows_tools`:

```python
def test_supervisor_prefers_evidence_grounding_evolution_when_plan_allows_tools(tmp_path):
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
        allowed_tools=["repo_search"],
    )

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=6,
        max_matches=1,
        out_dir=tmp_path / "run",
        repo_search_paths=[repo],
        plan_config=plan,
    )

    evolution_tasks = [task for task in state.task_queue if task.kind == "evolution"]
    assert evolution_tasks
    assert evolution_tasks[-1].payload["strategy"] == "evidence_grounding"
    assert any(
        trace.agent == "evolution" and trace.action == "evidence_grounding"
        for trace in state.agent_traces
    )
    assert any(item.origin == "evolution:evidence_grounding" for item in state.hypotheses)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_prefers_evidence_grounding_evolution_when_plan_allows_tools`

Expected: FAIL because `_active_evolution_strategy()` currently selects the first configured strategy, `simplification`, for cycle 1.

- [x] **Step 3: Implement minimal selector change**

Update `_active_evolution_strategy(plan, cycle, use_grounded=False)` so, when grounded evidence is active and `_plan_allows_external_tools(plan)` is true, `evidence_grounding` is moved to the front of the strategy list if present or inserted if absent. Update the call site in `run_research_cycle()` to pass `use_grounded_review`.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_prefers_evidence_grounding_evolution_when_plan_allows_tools \
  tests/test_supervisor.py::test_supervisor_uses_plan_selected_evidence_grounding_evolution \
  tests/test_supervisor.py::test_supervisor_uses_plan_selected_evolution_strategy
```

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-evidence-evolution.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 96 and revise Phase 3 status to mention plan-driven evidence-grounded evolution when external tools and grounded evidence are present.

- [x] **Step 2: Mark this plan complete**

Replace task checkboxes with `[x]` after implementation and verification.

- [x] **Step 3: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-evidence-evolution.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
