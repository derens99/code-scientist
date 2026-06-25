# Plan-Driven Tool Observation Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make research plans with external tool evidence automatically run observation reviews over tool outputs.

**Architecture:** Reuse the existing deterministic `observation_review` mode, which already searches runtime, trace, repository, and `tool_result` evidence. Extend supervisor review-type selection so grounded runs whose `ResearchPlanConfig.allowed_tools` names external tools append `observation_review` in addition to the existing grounded `full_review` behavior. This makes reflection over tool output plan-driven without adding a new review implementation.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Review-Type Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing test**

Add `test_supervisor_adds_observation_review_when_plan_allows_tools`:

```python
def test_supervisor_adds_observation_review_when_plan_allows_tools(tmp_path):
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

    observation_reviews = [
        review for review in state.reviews if review.review_type == "observation_review"
    ]
    assert observation_reviews
    assert any(
        "Observation evidence" in finding
        for review in observation_reviews
        for finding in review.findings
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_adds_observation_review_when_plan_allows_tools`

Expected: FAIL because `_active_review_types()` currently appends `full_review` for grounded evidence but does not append `observation_review` for tool-enabled plans.

- [x] **Step 3: Implement minimal review selector change**

Update `_active_review_types(plan, use_grounded)` so, when grounded evidence is active and `_plan_allows_external_tools(plan)` is true, it appends `observation_review` if not already present.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_adds_observation_review_when_plan_allows_tools \
  tests/test_supervisor.py::test_supervisor_uses_observation_and_simulation_review_modes
```

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-tool-observation-review.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 97 and revise Phase 3 status to mention plan-driven observation reviews for external tool evidence.

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
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-tool-observation-review.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
