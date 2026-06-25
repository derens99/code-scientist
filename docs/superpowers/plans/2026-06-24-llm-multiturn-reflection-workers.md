# LLM Multi-Turn Reflection Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider-backed deep-verification and safety-review reflection behave more like the paper's multi-turn scientific workers instead of single-call schema adapters.

**Architecture:** Keep deterministic reflection modes unchanged. When `ReflectionAgent` has an LLM client and `review_with_type()` is called for `deep_verification` or `safety_review`, run three focused LLM turns, parse the final JSON review, and persist compact turn summaries in `Review.review_trace`.

**Tech Stack:** Python dataclasses, existing LLM client interface, pytest, `uv`.

---

### Task 1: LLM Deep Verification Uses Multiple Turns

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing LLM deep-verification test**

Add `test_llm_deep_verification_uses_multi_turn_worker_trace` to `tests/test_agents.py`.

Use a fake LLM that records prompts and returns:

```python
if "reflection turn 1 claim mechanism" in lowered:
    return "Mechanism check: the claim depends on benchmark-gated critique before patching."
if "reflection turn 2 assumption risk audit" in lowered:
    return "Risk audit: representative traces and source-safety checks are required."
if "reflection turn 3 benchmark validation synthesis" in lowered:
    return json.dumps({
        "decision": "revise",
        "scores": {"alignment": 5, "plausibility": 3, "novelty": 4, "testability": 5, "safety": 4},
        "strengths": ["Clear benchmark path."],
        "weaknesses": ["Needs external validation."],
        "safety_notes": ["Human review required."],
        "findings": ["Benchmark validation is not yet measured."],
        "confidence": 0.72,
        "requires_revision": True,
        "evidence_refs": ["ev-benchmark"],
    })
```

Assert:

```python
assert len(fake_llm.calls) == 3
assert review.review_type == "llm_deep_verification"
assert review.decision == "revise"
assert review.evidence_refs == ["ev-benchmark"]
assert any("LLM turn 1 claim mechanism" in line for line in review.review_trace)
assert any("LLM turn 2 assumption risk audit" in line for line in review.review_trace)
assert any("LLM turn 3 benchmark validation synthesis" in line for line in review.review_trace)
assert review.review_trace[-1].startswith("LLM multi-turn reflection assessment:")
```

- [x] **Step 2: Run the deep-verification test to verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_deep_verification_uses_multi_turn_worker_trace -q
```

Expected: FAIL because `_review_with_llm()` currently makes one generic reflection call for `deep_verification`.

- [x] **Step 3: Implement LLM deep-verification worker**

In `ReflectionAgent.review_with_type`, route LLM-backed `deep_verification` to a new helper before `_review_with_llm`.

The helper should:

- collect evidence using `evidence_store.search_hypothesis(hypothesis, limit=5)` when available;
- call prompts containing `Reflection turn 1 claim mechanism`, `Reflection turn 2 assumption risk audit`, and `Reflection turn 3 benchmark validation synthesis`;
- parse the final JSON review with the same schema as `_review_with_llm`;
- set `review_type` to `llm_deep_verification`;
- append compact LLM turn summaries plus `LLM multi-turn reflection assessment: ...` to `review_trace`.

- [x] **Step 4: Run the deep-verification test to verify green**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_deep_verification_uses_multi_turn_worker_trace -q
```

Expected: PASS.

### Task 2: LLM Safety Review Uses Multiple Red-Team Turns

**Files:**
- Modify: `tests/test_agents.py`
- Modify: `src/code_scientist/agents.py`

- [x] **Step 1: Write the failing LLM safety-review test**

Add `test_llm_safety_review_uses_multi_turn_red_team_trace` to `tests/test_agents.py`.

Use a fake LLM that returns free-text for the first two prompts and final JSON for the third:

```python
if "reflection turn 1 autonomy and deployment red team" in lowered:
    return "Autonomy check: require human approval before repo mutation."
if "reflection turn 2 data and source-injection red team" in lowered:
    return "Data/source check: retrieved evidence must not override system instructions."
if "reflection turn 3 safety synthesis" in lowered:
    return json.dumps({
        "decision": "revise",
        "scores": {"alignment": 4, "plausibility": 4, "novelty": 4, "testability": 4, "safety": 2},
        "strengths": ["Useful safety boundary."],
        "weaknesses": ["Needs explicit source-injection mitigation."],
        "safety_notes": ["Gate all code changes behind human review."],
        "findings": ["Source-injection risk must be mitigated before deployment."],
        "confidence": 0.81,
        "requires_revision": True,
        "evidence_refs": ["ev-source"],
    })
```

Assert:

```python
assert len(fake_llm.calls) == 3
assert review.review_type == "llm_safety_review"
assert review.scores["safety"] == 2
assert any("LLM turn 1 autonomy and deployment red team" in line for line in review.review_trace)
assert any("LLM turn 2 data and source-injection red team" in line for line in review.review_trace)
assert any("LLM turn 3 safety synthesis" in line for line in review.review_trace)
```

- [x] **Step 2: Run the safety-review test to verify red**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_safety_review_uses_multi_turn_red_team_trace -q
```

Expected: FAIL because `_review_with_llm()` currently makes one generic reflection call for `safety_review`.

- [x] **Step 3: Implement LLM safety-review worker**

Add a helper for LLM-backed `safety_review` that:

- collects evidence using `evidence_store.search_hypothesis(hypothesis, limit=5)` when available;
- calls prompts containing `Reflection turn 1 autonomy and deployment red team`, `Reflection turn 2 data and source-injection red team`, and `Reflection turn 3 safety synthesis`;
- parses the final JSON review;
- sets `review_type` to `llm_safety_review`;
- appends compact turn summaries and the final multi-turn assessment to `review_trace`.

- [x] **Step 4: Run focused reflection tests to verify green**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_deep_verification_uses_multi_turn_worker_trace tests/test_agents.py::test_llm_safety_review_uses_multi_turn_red_team_trace -q
```

Expected: PASS.

### Task 3: Roadmap And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`
- Modify: `docs/superpowers/plans/2026-06-24-llm-multiturn-reflection-workers.md`

- [x] **Step 1: Update roadmap**

Add slice 114:

```markdown
114. Add provider-backed multi-turn reflection workers for deep verification and safety review, with auditable claim/risk/benchmark and red-team/safety synthesis traces.
```

Update implementation-status wording from slices `1-113` to `1-114` and narrow the remaining single-call worker gap accordingly.

- [x] **Step 2: Full verification**

Run:

```bash
uv run pytest tests/test_agents.py::test_llm_deep_verification_uses_multi_turn_worker_trace tests/test_agents.py::test_llm_safety_review_uses_multi_turn_red_team_trace -q
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
uv run python -m py_compile src/code_scientist/agents.py
```

Expected: all commands pass.

- [x] **Step 3: Mark plan complete**

Mark checkboxes complete only after the corresponding red, green, roadmap, and full verification steps have passed.
