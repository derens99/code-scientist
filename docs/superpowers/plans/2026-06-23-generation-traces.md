# Generation Traces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve an inspectable generation worker trace for each hypothesis so generated ideas show objective framing, evidence scan, and proposal synthesis steps.

**Architecture:** Add a backward-compatible `Hypothesis.generation_trace` list. Populate deterministic generation and grounded generation traces without changing existing hypothesis IDs or scoring. Render generation traces in markdown reports and the workbench hypothesis detail panel.

**Tech Stack:** Python dataclasses, `GenerationAgent`, markdown reporting, Next/Mantine workbench types and rendering, pytest/Vitest.

---

### Task 1: Persist And Populate Generation Traces

**Files:**
- Modify: `src/code_scientist/models.py`
- Modify: `src/code_scientist/agents.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write failing tests**

Add a `Hypothesis` round-trip/default test for `generation_trace`, plus generation-agent tests that assert deterministic and grounded generation record objective framing, evidence scan/retrieval, proposal synthesis, and assessment lines.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest -q tests/test_models.py::test_hypothesis_round_trips_generation_trace_and_loads_old_defaults tests/test_agents.py::test_generation_records_multi_turn_generation_trace tests/test_agents.py::test_grounded_generation_extends_generation_trace_with_retrieval`

Expected: FAIL because `Hypothesis` has no `generation_trace`.

- [ ] **Step 3: Implement minimal tracing**

Add `generation_trace` to `Hypothesis`, default it in `from_dict`, populate it in deterministic generation, preserve/extend it in grounded generation, and allow LLM JSON to optionally supply it.

- [ ] **Step 4: Verify focused tests pass**

Run the same focused pytest command. Expected: PASS.

### Task 2: Render And Verify

**Files:**
- Modify: `src/code_scientist/reporting.py`
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/components/HypothesisDetail.tsx`
- Modify: `tests/test_reporting.py`
- Modify: `web/src/components/HypothesisDetail.test.ts`
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Add report and UI failing tests**

Assert `render_report()` and `HypothesisDetail` include `Generation trace`.

- [ ] **Step 2: Implement rendering and documentation updates**

Render traces in the ranked hypothesis section and hypothesis detail, then update the paper gap analysis and completed slice list.

- [ ] **Step 3: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
git diff --check
```

Expected: all commands exit 0.
