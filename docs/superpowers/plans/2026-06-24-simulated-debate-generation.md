# Simulated Debate Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `simulated_debate` generation method synthesize hypotheses through an inspectable debate-style generation trace instead of falling back to generic relabeled blueprints.

**Architecture:** Keep the existing `Hypothesis.generation_trace` field and `ResearchPlanConfig.generation_methods` workflow. Add a deterministic `simulated_debate` mode that records pro, critique, rebuttal, synthesis, and assessment turns, carries evidence refs, and marks origin as `generation:simulated_debate`. Supervisor already dispatches configured generation methods, so the mode should flow through existing task traces.

**Tech Stack:** Python dataclasses, `GenerationAgent`, `run_research_cycle`, pytest.

---

### Task 1: Agent Mode Behavior

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [ ] **Step 1: Write the failing test**

Add `test_generation_supports_simulated_debate_mode_with_trace` that calls `GenerationAgent().generate_with_mode(..., mode="simulated_debate")` and asserts origin, trace rounds, evidence refs, and testability.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_agents.py::test_generation_supports_simulated_debate_mode_with_trace`

Expected: FAIL because current fallback does not include debate trace lines.

- [ ] **Step 3: Implement minimal mode**

Add a `simulated_debate` branch in `generate_with_mode()` and a helper that derives candidates from deterministic base generation while adding debate-specific rationale, assumptions, risks, and generation trace lines.

- [ ] **Step 4: Verify focused test passes**

Run the same focused pytest command. Expected: PASS.

### Task 2: Supervisor And Documentation

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Add supervisor assertion**

Extend `test_supervisor_uses_multi_round_debate_when_plan_requests_simulated_debate` so it also asserts a generated hypothesis has `origin == "generation:simulated_debate"` and debate trace lines.

- [ ] **Step 2: Run focused supervisor test**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_uses_multi_round_debate_when_plan_requests_simulated_debate`

Expected: PASS after implementation.

- [ ] **Step 3: Update gap analysis**

Record the new completed slice and revise generation-agent wording to include deterministic simulated debate generation.

- [ ] **Step 4: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
git diff --check
```

Expected: all commands exit 0.
