# Plan-Driven Simulation Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make research plans with benchmark or simulation tools automatically run simulation reviews over grounded benchmark evidence.

**Architecture:** Reuse the existing deterministic `simulation_review` mode, which already retrieves simulation, benchmark, prospective, scaling, pass-rate, and regression evidence. Extend supervisor review-type selection so grounded runs whose `ResearchPlanConfig.allowed_tools` names benchmark/simulation/evaluation tools append `simulation_review`. This keeps paper-aligned validation behavior plan-driven without introducing a new reviewer.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Review-Type Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing test**

Add `test_supervisor_adds_simulation_review_when_plan_allows_benchmark_tools`:

```python
def test_supervisor_adds_simulation_review_when_plan_allows_benchmark_tools(tmp_path):
    evidence = tmp_path / "benchmarks.md"
    evidence.write_text(
        "Benchmark candidate_metrics pass_rate=0.67 baseline_metrics pass_rate=0.42 "
        "with regression_count unchanged for assumption audits.",
        encoding="utf-8",
    )
    objective = "Find testable ideas to improve LLM coding agents"
    goal = ResearchGoal.from_objective(objective)
    plan = replace(
        ResearchPlanConfig.from_goal(goal),
        allowed_tools=["benchmark_runner"],
    )

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=6,
        max_matches=1,
        out_dir=tmp_path / "run",
        evidence_paths=[evidence],
        plan_config=plan,
    )

    simulation_reviews = [
        review for review in state.reviews if review.review_type == "simulation_review"
    ]
    assert simulation_reviews
    assert any(
        "simulation evidence" in finding.lower()
        for review in simulation_reviews
        for finding in review.findings
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_adds_simulation_review_when_plan_allows_benchmark_tools`

Expected: FAIL because `_active_review_types()` currently appends `full_review` for grounded evidence and `observation_review` for external tools, but it does not append `simulation_review` for benchmark-capable plans.

- [x] **Step 3: Implement minimal selector change**

Add a helper such as `_plan_allows_benchmark_tools(plan)` that detects normalized allowed tool names containing benchmark, simulation, simulator, eval, evaluation, or metric runner signals. Update `_active_review_types()` to append `simulation_review` when grounded evidence is active and that helper returns true.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_adds_simulation_review_when_plan_allows_benchmark_tools \
  tests/test_supervisor.py::test_supervisor_uses_observation_and_simulation_review_modes
```

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-simulation-review.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 98 and revise Phase 3 status to mention plan-driven simulation reviews for benchmark/simulation tool plans.

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
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-simulation-review.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
