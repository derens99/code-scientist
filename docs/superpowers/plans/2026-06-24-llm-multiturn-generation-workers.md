# LLM Multi-Turn Generation Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider-backed generation modes behave more like the paper's multi-turn scientific workers instead of single-call hypothesis adapters.

**Architecture:** Keep the deterministic generation paths unchanged. When `GenerationAgent` has an LLM client and `generate_with_mode()` is called for `simulated_debate`, `multi_round_debate`, `multi_turn_debate`, or `tool_augmented_generation`, run a three-turn LLM workflow and persist compact turn summaries in each generated hypothesis' `generation_trace`.

**Tech Stack:** Python dataclasses, existing LLM client interface, pytest, `uv`.

---

### Task 1: LLM Simulated Debate Generation Uses Multiple Turns

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing LLM simulated-debate test**

Add a test named `test_llm_generation_simulated_debate_mode_uses_multi_turn_worker_trace` to `tests/test_agents.py`.

The fake LLM should record prompts. It should return free-text for the first two prompts and final valid hypothesis JSON for the third prompt:

```python
def complete(self, prompt, max_tokens):
    self.calls.append((prompt, max_tokens))
    lowered = prompt.lower()
    if "generation turn 1 debate proposal" in lowered:
        return "Proposal: use debate to expose patch-risk assumptions."
    if "generation turn 2 debate critique" in lowered:
        return "Critique: the proposal needs benchmark evidence and source-safety checks."
    if "generation turn 3 debate synthesis" in lowered:
        return json.dumps(
            {
                "hypotheses": [
                    {
                        "title": "Debate-traced patch risk review",
                        "claim": "A debate-traced patch-risk review will reduce regressions in LLM coding-agent repairs.",
                        "rationale": "The critique turn forces assumptions and benchmark checks before ranking.",
                        "assumptions": ["Benchmark traces cover representative patch risks."],
                        "risks": ["extra review latency"],
                    }
                ]
            }
        )
    raise AssertionError(prompt)
```

Assert:

```python
assert len(fake_llm.calls) == 3
assert hypotheses[0].origin == "anthropic-haiku:simulated_debate"
assert any("LLM turn 1 debate proposal" in line for line in hypotheses[0].generation_trace)
assert any("LLM turn 2 debate critique" in line for line in hypotheses[0].generation_trace)
assert any("LLM turn 3 debate synthesis" in line for line in hypotheses[0].generation_trace)
assert hypotheses[0].generation_trace[-1].startswith("LLM multi-turn generation assessment:")
```

- [x] **Step 2: Run the simulated-debate test to verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_generation_simulated_debate_mode_uses_multi_turn_worker_trace -q
```

Expected: FAIL because `generate_with_mode(..., mode="simulated_debate")` currently uses deterministic debate wrapping even when an LLM client is present.

- [x] **Step 3: Implement the LLM simulated-debate worker**

In `GenerationAgent.generate_with_mode`, before the deterministic `simulated_debate` branch, route LLM-backed debate modes to a new private method.

Add helper methods/functions that:

- call the LLM with a prompt containing `Generation turn 1 debate proposal`;
- call the LLM with a prompt containing `Generation turn 2 debate critique`;
- call the LLM with a prompt containing `Generation turn 3 debate synthesis`;
- parse the final response with `_parse_llm_hypotheses(..., origin=f"{self.llm_origin}:{mode}")`;
- append compact trace lines for all three turns plus `LLM multi-turn generation assessment: ...`.

Keep JSON-repair behavior for the final synthesis response by reusing the existing repair prompt on parse failure.

- [x] **Step 4: Run the simulated-debate test to verify green**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_generation_simulated_debate_mode_uses_multi_turn_worker_trace -q
```

Expected: PASS.

### Task 2: LLM Tool-Augmented Generation Uses Multiple Turns

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing LLM tool-generation test**

Add a test named `test_llm_generation_tool_augmented_mode_uses_tool_observation_turns` to `tests/test_agents.py`.

Use an `EvidenceStore` with one `tool_result_repo_search` evidence item. The fake LLM should return free-text for the first two prompts and final valid hypothesis JSON for the third prompt. Assert:

```python
assert len(fake_llm.calls) == 3
assert hypotheses[0].origin == "anthropic-haiku:tool_augmented_generation"
assert hypotheses[0].evidence_refs == ["ev-repo-tool"]
assert any("LLM turn 1 tool query plan" in line for line in hypotheses[0].generation_trace)
assert any("LLM turn 2 tool observation analysis" in line for line in hypotheses[0].generation_trace)
assert any("LLM turn 3 tool synthesis" in line for line in hypotheses[0].generation_trace)
```

- [x] **Step 2: Run the tool-generation test to verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_generation_tool_augmented_mode_uses_tool_observation_turns -q
```

Expected: FAIL because tool-augmented mode is currently deterministic even with an LLM client.

- [x] **Step 3: Implement the LLM tool-augmented worker**

Add LLM-backed `tool_augmented_generation` routing in `GenerationAgent.generate_with_mode`.

The helper should:

- select tool evidence from the `EvidenceStore` using the same `_is_tool_evidence` predicate and retrieval preference as the deterministic path;
- call prompts containing `Generation turn 1 tool query plan`, `Generation turn 2 tool observation analysis`, and `Generation turn 3 tool synthesis`;
- parse final JSON with origin `f"{self.llm_origin}:tool_augmented_generation"`;
- pass selected tool evidence into `_parse_llm_hypotheses` so evidence refs remain tool evidence ids;
- append compact trace lines for all three turns and the final multi-turn assessment.

- [x] **Step 4: Run focused generation tests to verify green**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_generation_simulated_debate_mode_uses_multi_turn_worker_trace tests/test_agents.py::test_llm_generation_tool_augmented_mode_uses_tool_observation_turns -q
```

Expected: PASS.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-llm-multiturn-generation-workers.md`

- [x] **Step 1: Update roadmap**

Add slice 113:

```markdown
113. Add provider-backed multi-turn generation workers for simulated debate and tool-augmented generation, with auditable LLM proposal/critique/synthesis or query/observation/synthesis traces.
```

Update implementation-status wording from slices `1-112` to `1-113` and note that this reduces, but does not eliminate, the remaining gap around deeper multi-turn scientific workers.

- [x] **Step 2: Full verification**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_generation_simulated_debate_mode_uses_multi_turn_worker_trace tests/test_agents.py::test_llm_generation_tool_augmented_mode_uses_tool_observation_turns -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands pass.

- [x] **Step 3: Mark plan complete**

Mark checkboxes complete only after the corresponding red, green, roadmap, and full verification steps have passed.
