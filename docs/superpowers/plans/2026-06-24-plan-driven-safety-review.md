# Plan-Driven Safety Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make research plans that use untrusted external or tool-sourced evidence automatically run safety reviews when grounded evidence is present.

**Architecture:** Reuse the existing deterministic `safety_review` mode, which already records autonomy/deployment, data/credential, and source-injection/benchmark-gaming red-team turns. Extend supervisor review-type selection with a plan-intent helper that inspects `ResearchPlanConfig.allowed_tools` and `allowed_sources`, then appends `safety_review` only for grounded plans that advertise web/search/repo/literature/private/tool sources and do not already include safety review.

**Tech Stack:** Python dataclasses, `ResearchPlanConfig`, `run_research_cycle`, pytest.

---

### Task 1: Review-Type Selection

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`

- [x] **Step 1: Write the failing tests**

Add `test_supervisor_adds_safety_review_for_untrusted_external_sources`:

```python
def test_supervisor_adds_safety_review_for_untrusted_external_sources(tmp_path):
    evidence = tmp_path / "web-source.md"
    evidence.write_text(
        "External web source: coding-agent repair traces can include credential exposure, "
        "deployment boundary mistakes, and prompt injection benchmark-gaming instructions.",
        encoding="utf-8",
    )
    objective = "Find testable ideas to improve LLM coding agents"
    goal = ResearchGoal.from_objective(objective)
    plan = replace(
        ResearchPlanConfig.from_goal(goal),
        review_types=["novelty_review"],
        allowed_sources=["web_search_result", "web_search_document_span"],
        allowed_tools=["web_search"],
    )

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=4,
        max_matches=1,
        out_dir=tmp_path / "run",
        evidence_paths=[evidence],
        plan_config=plan,
    )

    safety_reviews = [
        review for review in state.reviews if review.review_type == "safety_review"
    ]
    assert safety_reviews
    assert any(
        "source injection and benchmark gaming" in trace.lower()
        for review in safety_reviews
        for trace in review.review_trace
    )
```

Add `test_supervisor_does_not_add_safety_review_for_default_local_sources`:

```python
def test_supervisor_does_not_add_safety_review_for_default_local_sources(tmp_path):
    evidence = tmp_path / "local-notes.md"
    evidence.write_text(
        "Local evidence: assumption checks caught stale call-path facts in repair traces.",
        encoding="utf-8",
    )
    objective = "Find testable ideas to improve LLM coding agents"
    goal = ResearchGoal.from_objective(objective)
    plan = replace(
        ResearchPlanConfig.from_goal(goal),
        review_types=["novelty_review"],
    )

    state = run_research_cycle(
        objective=objective,
        cycles=1,
        max_hypotheses=4,
        max_matches=1,
        out_dir=tmp_path / "run",
        evidence_paths=[evidence],
        plan_config=plan,
    )

    assert "safety_review" not in {review.review_type for review in state.reviews}
```

- [x] **Step 2: Run tests to verify the external-source test fails**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_adds_safety_review_for_untrusted_external_sources \
  tests/test_supervisor.py::test_supervisor_does_not_add_safety_review_for_default_local_sources
```

Expected: FAIL because `_active_review_types()` currently respects the narrowed `review_types=["novelty_review"]` plan and does not append `safety_review` for untrusted source plans. The default-local guard should pass or continue passing.

- [x] **Step 3: Implement minimal selector change**

Add `_plan_needs_safety_review(plan)` near the existing plan-intent helpers:

```python
def _plan_needs_safety_review(plan: ResearchPlanConfig) -> bool:
    normalized = {
        value.strip().lower().replace("-", "_")
        for value in [*plan.allowed_tools, *plan.allowed_sources]
        if value.strip()
    }
    inert = {"deterministic_agents", "deterministic_agent", "seed_paper_evidence", "local_evidence_paths"}
    markers = (
        "web",
        "search",
        "repo",
        "repository",
        "tool",
        "openalex",
        "literature",
        "full_text",
        "private",
        "indexed",
        "crawl",
        "url",
    )
    return any(value not in inert and any(marker in value for marker in markers) for value in normalized)
```

Then update `_active_review_types()`:

```python
if use_grounded and _plan_needs_safety_review(plan) and "safety_review" not in review_types:
    review_types.append("safety_review")
```

Place this before deep/observation/simulation additions so safety red-team traces precede source-specific reflection.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_supervisor.py::test_supervisor_adds_safety_review_for_untrusted_external_sources \
  tests/test_supervisor.py::test_supervisor_does_not_add_safety_review_for_default_local_sources \
  tests/test_supervisor.py::test_supervisor_adds_deep_verification_for_literature_validation_sources \
  tests/test_supervisor.py::test_supervisor_adds_observation_review_when_plan_allows_tools
```

Expected: PASS.

### Task 2: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-plan-driven-safety-review.md`

- [x] **Step 1: Update gap analysis**

Record completed slice 100 and revise Phase 3/Safety status to mention plan-driven safety reviews for untrusted external or tool-sourced grounded evidence.

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
rg -n "[[:blank:]]$" src/code_scientist/supervisor.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-plan-driven-safety-review.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
