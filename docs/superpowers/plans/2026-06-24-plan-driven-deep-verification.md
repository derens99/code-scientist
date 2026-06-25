# Plan-Driven Deep Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make research plans with literature, benchmark, evaluation, or validation sources automatically run deep verification when grounded evidence is present.

**Architecture:** Reuse the existing deterministic `deep_verification` review mode, which already performs claim-mechanism, assumption/risk, and benchmark-validation evidence queries. Extend supervisor review-type selection with a small plan-intent helper that inspects `ResearchPlanConfig.allowed_tools` and `allowed_sources`, then appends `deep_verification` only for grounded runs that advertise literature/benchmark/validation-grade evidence.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Review-Type Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing test**

Add `test_supervisor_adds_deep_verification_for_literature_validation_sources`:

```python
def test_supervisor_adds_deep_verification_for_literature_validation_sources(tmp_path):
    evidence = tmp_path / "literature-validation.md"
    evidence.write_text(
        "Literature mechanism evidence: critic-before-edit agents improve repair quality "
        "when mechanism evidence is checked against prior work.\n"
        "Assumption evidence: stale call-path assumptions and risky benchmark shortcuts "
        "cause regression failures in coding-agent repair traces.\n"
        "Benchmark validation evidence: candidate_metrics pass_rate=0.67 baseline_metrics "
        "pass_rate=0.42 with regression_count unchanged.",
        encoding="utf-8",
    )
    objective = "Find testable ideas to improve LLM coding agents"
    goal = ResearchGoal.from_objective(objective)
    plan = replace(
        ResearchPlanConfig.from_goal(goal),
        allowed_tools=["openalex_literature_search"],
        allowed_sources=["literature_full_text", "benchmark_results"],
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

    verification_reviews = [
        review for review in state.reviews if review.review_type == "deep_verification"
    ]
    assert verification_reviews
    assert any(review.evidence_refs for review in verification_reviews)
    assert any(
        "turn 3 query (benchmark validation)" in trace.lower()
        for review in verification_reviews
        for trace in review.review_trace
    )
```

Also add `test_supervisor_does_not_add_deep_verification_for_default_seed_sources`:

```python
def test_supervisor_does_not_add_deep_verification_for_default_seed_sources(tmp_path):
    evidence = tmp_path / "local-observation.md"
    evidence.write_text(
        "Local observation: repair traces show assumption checks catch stale call-path facts.",
        encoding="utf-8",
    )
    objective = "Find testable ideas to improve LLM coding agents"

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=4,
        max_matches=1,
        out_dir=tmp_path / "run",
        evidence_paths=[evidence],
    )

    assert "deep_verification" not in {review.review_type for review in state.reviews}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_supervisor.py::test_supervisor_adds_deep_verification_for_literature_validation_sources
```

Expected: the literature/validation test fails because `_active_review_types()` currently appends `full_review`, `observation_review`, and `simulation_review` for some grounded plans, but it does not infer `deep_verification` from literature/benchmark validation sources. The default-source regression must fail before removing overly broad source markers if a marker such as `paper` accidentally matches default `seed_paper_evidence`.

- [x] **Step 3: Implement minimal selector change**

Add `_plan_needs_deep_verification(plan)` near the existing plan-intent helpers:

```python
def _plan_needs_deep_verification(plan: ResearchPlanConfig) -> bool:
    normalized = {
        value.strip().lower().replace("-", "_")
        for value in [*plan.allowed_tools, *plan.allowed_sources]
        if value.strip()
    }
    markers = (
        "literature",
        "publication",
        "full_text",
        "openalex",
        "benchmark",
        "simulation",
        "simulator",
        "eval",
        "evaluation",
        "metric",
        "validation",
        "verification",
    )
    return any(any(marker in value for marker in markers) for value in normalized)
```

Then update `_active_review_types()`:

```python
if use_grounded and _plan_needs_deep_verification(plan) and "deep_verification" not in review_types:
    review_types.append("deep_verification")
```

Place this before observation/simulation additions so deeper verification appears before source-specific reviews.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_adds_deep_verification_for_literature_validation_sources \
  tests/test_supervisor.py::test_supervisor_adds_simulation_review_when_plan_allows_benchmark_tools \
  tests/test_supervisor.py::test_supervisor_adds_observation_review_when_plan_allows_tools
```

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-deep-verification.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 99 and revise Phase 3 status to mention plan-driven deep verification for literature/benchmark/validation grounded plans.

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
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-deep-verification.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
