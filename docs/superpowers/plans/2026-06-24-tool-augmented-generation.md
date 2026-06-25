# Tool-Augmented Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a selectable generation mode that turns retrieved tool evidence into hypotheses with auditable tool-use trace lines.

**Architecture:** Reuse `EvidenceStore`, `Evidence.metadata["tool"]`, and `Hypothesis.generation_trace` instead of adding a new tool runner. `GenerationAgent.generate_with_mode(..., mode="tool_augmented_generation")` will retrieve tool-origin evidence, synthesize deterministic hypotheses from it, and emit trace turns for tool query, tool observation, proposal synthesis, and assessment. Supervisor routing already dispatches configured generation methods, but it must pass the evidence store for this mode just like literature-grounded generation.

**Tech Stack:** Python dataclasses, `GenerationAgent`, `EvidenceStore`, `run_research_cycle`, pytest.

---

### Task 1: Agent Mode Behavior

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing test**

Add `test_generation_supports_tool_augmented_generation_mode_with_trace`:

```python
def test_generation_supports_tool_augmented_generation_mode_with_trace():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    store = EvidenceStore(
        [
            Evidence(
                id="ev-repo-tool",
                kind="tool_result_repo_search",
                source="src/agent.py",
                content="Repository trace shows failed patch recovery improves after assumption audits.",
                notes="repo search hit",
                metadata={"tool": "repo_search", "query": "failed patch recovery"},
            )
        ]
    )

    hypotheses = GenerationAgent().generate_with_mode(
        goal,
        store,
        mode="tool_augmented_generation",
        limit=1,
    )

    assert len(hypotheses) == 1
    hypothesis = hypotheses[0]
    assert hypothesis.origin == "generation:tool_augmented_generation"
    assert hypothesis.evidence_refs == ["ev-repo-tool"]
    assert "tool" in hypothesis.title.lower()
    assert any("Tool turn 1 query" in line for line in hypothesis.generation_trace)
    assert any("Tool turn 2 observation" in line for line in hypothesis.generation_trace)
    assert any("Tool turn 3 proposal synthesis" in line for line in hypothesis.generation_trace)
    assert hypothesis.generation_trace[-1].startswith("Tool generation assessment:")
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_agents.py::test_generation_supports_tool_augmented_generation_mode_with_trace`

Expected: FAIL because the mode currently falls back to generic relabeled blueprints and does not cite the tool evidence or emit tool trace lines.

- [x] **Step 3: Implement minimal agent mode**

Add a `tool_augmented_generation` branch in `GenerationAgent.generate_with_mode()` and a `_tool_augmented_hypotheses(goal, evidence_store, limit)` helper that filters evidence with `metadata["tool"]` or tool-like `kind`, builds one hypothesis per selected evidence record, cites that evidence id, and emits tool trace lines.

- [x] **Step 4: Verify focused agent test passes**

Run: `uv run pytest -q tests/test_agents.py::test_generation_supports_tool_augmented_generation_mode_with_trace`

Expected: PASS.

### Task 2: Supervisor Routing And Documentation

**Files:**
- Modify: `tests/test_supervisor.py`
- Modify: `src/code_scientist/supervisor.py`
- Modify: `docs/paper-implementation-gap-analysis.md`

- [x] **Step 1: Write supervisor regression test**

Add `test_supervisor_routes_tool_augmented_generation_through_evidence_store` that creates a plan with `generation_methods=["tool_augmented_generation"]`, passes a local evidence file plus repository-search path or direct evidence source that creates tool evidence, runs one cycle, and asserts a produced hypothesis has `origin == "generation:tool_augmented_generation"` plus a `Tool turn 2 observation` trace.

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_supervisor.py::test_supervisor_routes_tool_augmented_generation_through_evidence_store`

Expected: FAIL until `_generate_for_plan()` passes `EvidenceStore` for `tool_augmented_generation`.

- [x] **Step 3: Implement supervisor routing**

Update `_generate_for_plan()` so modes in `{"literature_grounded_generation", "tool_augmented_generation"}` receive `evidence_store`; other modes retain the existing list source unless grounded review is active.

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q \
  tests/test_agents.py::test_generation_supports_tool_augmented_generation_mode_with_trace \
  tests/test_supervisor.py::test_supervisor_routes_tool_augmented_generation_through_evidence_store
```

Expected: PASS.

- [x] **Step 5: Update gap analysis**

Record completed slice 94, update the generation-agent row and Phase 3 status to mention deterministic tool-augmented generation, and narrow the remaining gap wording to tool-using generation beyond deterministic tool-evidence synthesis.

- [x] **Step 6: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
rg -n "[[:blank:]]$" src/code_scientist/agents.py src/code_scientist/supervisor.py tests/test_agents.py tests/test_supervisor.py docs/paper-implementation-gap-analysis.md docs/superpowers/plans/2026-06-24-tool-augmented-generation.md
```

Expected: all commands exit 0 except the trailing-whitespace `rg`, which exits 1 with no output when clean.
