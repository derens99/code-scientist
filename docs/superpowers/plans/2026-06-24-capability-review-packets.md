# Capability Review Packets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI-accessible blinded review packet for baseline-vs-Code Scientist capability evaluation artifacts.

**Architecture:** Reuse the existing feedback-loop review packet pattern in `src/code_scientist/evaluation.py`: public anonymous arms, private answer key, and score template. Add a CLI command that writes the three JSON files and tests that the public packet does not expose provenance labels.

**Tech Stack:** Python, argparse, pytest, existing JSON fixture helpers.

---

### Task 1: Capability Packet Tests

**Files:**
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing evaluation test**

Add `build_capability_review_packet` to the import list in `tests/test_evaluation.py`, then add:

```python
def test_build_capability_review_packet_blinds_baseline_and_code_scientist_arms():
    spec = {
        "goal_id": "goal-1",
        "objective": "Improve coding-agent research loops.",
        "baseline_name": "single_shot_llm",
        "metrics": ["novelty", "plausibility", "impact", "testability", "safety"],
        "artifact_refs": ["runs/baseline/state.json", "runs/code-scientist/state.json"],
        "review_items": [
            {
                "item_id": "hyp-1",
                "prompt": "Score each arm against the rubric.",
                "baseline_artifact": {"title": "Baseline", "claim": "Use one prompt."},
                "code_scientist_artifact": {
                    "hypothesis_id": "hyp-1",
                    "title": "Code Scientist",
                    "claim": "Use retrieved evidence and critique loops.",
                },
            }
        ],
    }

    packet, answer_key, score_template = build_capability_review_packet(spec, seed="paper-gap")

    item = packet["review_items"][0]
    key_item = answer_key["answer_key"]["hyp-1"]
    template_item = score_template["review_items"][0]
    assert packet["goal_id"] == "goal-1"
    assert packet["baseline_name"] == "single_shot_llm"
    assert set(item["arms"]) == {"arm_a", "arm_b"}
    assert "baseline_label" not in item
    assert "code_scientist_label" not in item
    assert key_item["baseline_label"] in {"arm_a", "arm_b"}
    assert key_item["code_scientist_label"] in {"arm_a", "arm_b"}
    assert key_item["baseline_label"] != key_item["code_scientist_label"]
    assert key_item["hypothesis_id"] == "hyp-1"
    assert template_item["scores"] == {
        "arm_a": {"novelty": None, "plausibility": None, "impact": None, "testability": None, "safety": None},
        "arm_b": {"novelty": None, "plausibility": None, "impact": None, "testability": None, "safety": None},
    }
```

- [ ] **Step 2: Write the failing CLI test**

Add this test near the feedback-loop packet CLI test in `tests/test_cli.py`:

```python
def test_cli_capability_review_packet_writes_blinded_packet_template_and_key(tmp_path):
    spec = tmp_path / "capability-packet-spec.json"
    spec.write_text(
        json.dumps(
            {
                "goal_id": "goal-1",
                "objective": "Improve coding-agent research loops.",
                "baseline_name": "single_shot_llm",
                "metrics": ["novelty", "impact"],
                "review_items": [
                    {
                        "item_id": "hyp-1",
                        "baseline_artifact": {"title": "Baseline"},
                        "code_scientist_artifact": {"hypothesis_id": "hyp-1", "title": "Candidate"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "capability-review-packet"

    exit_code = main(["capability-review-packet", str(spec), "--out", str(out_dir), "--seed", "paper-gap"])

    packet = json.loads((out_dir / "capability-review-packet.json").read_text(encoding="utf-8"))
    answer_key = json.loads((out_dir / "capability-review-answer-key.json").read_text(encoding="utf-8"))
    score_template = json.loads((out_dir / "capability-review-score-template.json").read_text(encoding="utf-8"))
    item = packet["review_items"][0]
    assert exit_code == 0
    assert set(item["arms"]) == {"arm_a", "arm_b"}
    assert "baseline_label" not in item
    assert "code_scientist_label" not in item
    assert answer_key["answer_key"]["hyp-1"]["code_scientist_label"] in {"arm_a", "arm_b"}
    assert answer_key["answer_key"]["hyp-1"]["hypothesis_id"] == "hyp-1"
    assert score_template["review_items"][0]["scores"] == {
        "arm_a": {"novelty": None, "impact": None},
        "arm_b": {"novelty": None, "impact": None},
    }
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_build_capability_review_packet_blinds_baseline_and_code_scientist_arms tests/test_cli.py::test_cli_capability_review_packet_writes_blinded_packet_template_and_key -q
```

Expected: FAIL because `build_capability_review_packet` and the `capability-review-packet` command do not exist.

### Task 2: Capability Packet Implementation

**Files:**
- Modify: `src/code_scientist/evaluation.py`
- Modify: `src/code_scientist/cli.py`

- [ ] **Step 1: Implement `build_capability_review_packet`**

Add a function next to `build_feedback_loop_review_packet` that validates a JSON object with non-empty `review_items`, requires `metrics`, blinds `baseline_artifact` and `code_scientist_artifact` with `_blind_arm_labels`, and returns `(packet, answer_key, score_template)`.

- [ ] **Step 2: Add the CLI parser and command handler**

Import `build_capability_review_packet`, add a `capability-review-packet SPEC_JSON --out DIR --seed ""` parser, and write:

```text
capability-review-packet.json
capability-review-answer-key.json
capability-review-score-template.json
```

- [ ] **Step 3: Run tests to verify green**

Run:

```bash
uv run pytest tests/test_evaluation.py::test_build_capability_review_packet_blinds_baseline_and_code_scientist_arms tests/test_cli.py::test_cli_capability_review_packet_writes_blinded_packet_template_and_key -q
```

Expected: PASS.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [ ] **Step 1: Update the gap-analysis document**

Update backend test count from 205 to 207 if full backend tests pass. Add the new capability review packet to the Evaluation status and implementation-slice list, while keeping the remaining gap explicit: reviewers still need to score the packet and those returned scores still need ingestion into paper-level capability study records.

- [ ] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
PATH=/opt/homebrew/bin:$PATH npm test
PATH=/opt/homebrew/bin:$PATH npm run build
PATH=/opt/homebrew/bin:$PATH npm run typecheck
git diff --check
```

Expected: all commands pass.
