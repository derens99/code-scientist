# Baseline Run Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic baseline-run path so benchmark comparison studies can create reproducible single-shot baseline states instead of requiring hand-authored baseline `state.json` files.

**Architecture:** Create `src/code_scientist/baselines.py` with `run_baseline_research`, producing a normal `RunState` containing baseline-origin hypotheses and no Code Scientist control-loop artifacts. Wire it through `code-scientist baseline-run`, and let `code-scientist benchmark-comparison-study` generate missing baseline states from manifest entries that provide `baseline_objective` and optional `baseline_method`.

**Tech Stack:** Python, existing `RunState`/`Hypothesis` models, argparse, JSON manifests, pytest.

---

### Task 1: Failing Tests

**Files:**
- Create: `tests/test_baselines.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add baseline module test**

Create `tests/test_baselines.py` with:

```python
from code_scientist.baselines import run_baseline_research


def test_run_baseline_research_creates_single_shot_state():
    state = run_baseline_research(
        "Improve LLM coding agents with retrieved evidence regression analysis",
        max_hypotheses=2,
    )

    assert state.goal.objective == "Improve LLM coding agents with retrieved evidence regression analysis"
    assert state.run_status == "completed"
    assert len(state.hypotheses) == 2
    assert {hypothesis.origin for hypothesis in state.hypotheses} == {"baseline:single_shot"}
    assert state.hypotheses[0].id.startswith("baseline-")
    assert "Baseline method: single_shot" in state.hypotheses[0].generation_trace
    assert state.hypotheses[0].test_plan.metrics == ["pass_rate", "regression_count"]
    assert state.task_queue == []
    assert state.matches == []
```

- [x] **Step 2: Add CLI baseline-run test**

Add `test_cli_baseline_run_writes_state_and_report` to `tests/test_cli.py`:

```python
exit_code = main([
    "baseline-run",
    "Improve LLM coding agents with retrieved evidence",
    "--max-hypotheses",
    "2",
    "--out",
    str(out_dir),
])

data = json.loads((out_dir / "state.json").read_text(encoding="utf-8"))
report = (out_dir / "report.md").read_text(encoding="utf-8")
assert exit_code == 0
assert len(data["hypotheses"]) == 2
assert data["hypotheses"][0]["origin"] == "baseline:single_shot"
assert "Baseline method: single_shot" in data["hypotheses"][0]["generation_trace"]
assert "Code Scientist Research Report" in report
```

- [x] **Step 3: Add benchmark-study generated-baseline test**

Add a CLI test where a `benchmark-comparison-study` manifest entry contains `baseline_objective` and `candidate_state`, but no `baseline_state`. Assert:

```python
assert (out_dir / "baselines" / "retrieval-generated" / "state.json").exists()
assert output["summary"]["comparison_count"] == 1
assert output["results"][0]["baseline_metrics"]["pass_rate"] == 0.0
```

- [x] **Step 4: Verify red**

Run:

```bash
uv run pytest tests/test_baselines.py::test_run_baseline_research_creates_single_shot_state tests/test_cli.py::test_cli_baseline_run_writes_state_and_report tests/test_cli.py::test_cli_benchmark_comparison_study_can_generate_baseline_state -q
```

Expected: FAIL because `code_scientist.baselines`, `baseline-run`, and manifest baseline generation do not exist.

### Task 2: Implementation

**Files:**
- Create: `src/code_scientist/baselines.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Implement baseline state generation**

Add:

```python
def run_baseline_research(
    objective: str,
    *,
    method: str = "single_shot",
    max_hypotheses: int = 1,
) -> RunState:
    ...
```

For now support only `single_shot`. Raise `ValueError` for unknown methods or `max_hypotheses < 1`. Create deterministic baseline hypotheses with `origin="baseline:single_shot"`, `generation_trace` that includes `Baseline method: single_shot`, and `TestPlan(metrics=["pass_rate", "regression_count"])`.

- [x] **Step 2: Add CLI `baseline-run`**

Add parser:

```bash
code-scientist baseline-run OBJECTIVE --method single_shot --max-hypotheses N --out out-dir
```

Handler writes `state.json` and `report.md`.

- [x] **Step 3: Generate missing baselines inside benchmark studies**

In `_benchmark_comparison_results_from_manifest`, if `baseline_state` is omitted:

- Require `baseline_objective`.
- Use `baseline_method` defaulting to `single_shot`.
- Use `baseline_max_hypotheses` defaulting to `1`.
- Write the generated baseline to `out/baselines/<comparison-id>/state.json`.
- Compare against that generated state.

- [x] **Step 4: Verify green**

Run the focused test command again and expect PASS.

### Task 3: Docs And Full Verification

**Files:**
- Modify: `docs/paper-implementation-gap-analysis.md`

- [x] **Step 1: Update roadmap status**

Add slice 108 for deterministic baseline-run generation. Update the Evaluation row/status wording to say benchmark studies can generate reproducible single-shot baseline states, while preserving the remaining gap that no real external benchmark study has been run.

- [x] **Step 2: Full verification**

Run:

```bash
uv run pytest -q
(cd web && PATH=/opt/homebrew/bin:$PATH npm test)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run build)
(cd web && PATH=/opt/homebrew/bin:$PATH npm run typecheck)
git diff --check
```

Expected: all commands pass.
