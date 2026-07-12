# Measured Validation Study (2026-07-12)

A complete, committed record of the first end-to-end measured validation run:
engine-generated hypothesis → independent packet review → instrument
calibration → pre-registered paired experiment on a real coding agent →
honest verdict. Everything here was produced by the pipeline itself; trial
workspaces were pruned from `experiments/*/trials/` to keep the example small
(each arm keeps its `agent-output.json`, `workspace-diff.txt`, and
`grader-output.txt`).

## The run

- **Objective**: find the single appended system-prompt instruction that most
  improves a small headless coding agent's held-out-test pass rate on tasks
  whose prompts do not themselves instruct verification.
- **Provider**: `host-agent` — the launching Claude Code session answered all
  51 engine LLM calls over the llm-bridge (`llm-bridge/responses/` is the
  audit trail). No API key was used anywhere in this study.
- **Outcome**: 4 hypotheses, 32 reviews (initial, full, three-turn deep
  verification, simulation), 4 mirrored debate matches with order-invariance
  checks, proximity clustering, meta-review. Top-ranked (Elo 1232):
  `hyp-a473177a6b6c` — *Requirement-Checklist Extraction Instruction Raises
  Held-Out Pass Rate*. An independent packet-reviewer subagent returned
  **revise** (`agent-packets/reviews/`), demanding a headroom gate, a concrete
  decision rule, and neutral task prompts — all adopted before execution.

## Instrument calibration (the saturation finding)

Baseline probes (Haiku subagents, fixed trial template, held-out grading)
saturated three successive instrument designs:

| instrument | baseline probes |
| --- | --- |
| `benchmarks/agent-tasks` (visible tests + test instruction) | 10/10 pass |
| `benchmarks/agent-tasks-noharness` (no tests, no instruction) | 10/10 pass |
| `benchmarks/agent-tasks-hard` (10–15 requirements/task) | 16/16 pass |

An unbounded-turn small agent with the spec colocated in the file it edits
self-verifies to ceiling on any single-function stdlib task. Headroom only
appeared with **requirement dispersion and time scarcity**:
`benchmarks/agent-task-bundles` packs three hard tasks into one trial under a
360-second budget with a pre-registered overtime-is-failure rule.

## The experiment

Protocol `exp-90368226dbba` (sha256 `9f6c2ee38a255d4c…`, registered before any
trial): 8 bundles × 3 paired trials = 24 pairs / 48 arms, seed 20260712,
candidate arm = baseline plus exactly the instruction text from the
hypothesis claim, one-sided exact McNemar at α=0.05, minimum 3 discordant
pairs, task-level sign test as robustness check.

**Result: `inconclusive` under the pre-registered rule, with a negative point
estimate.**

- Baseline pass rate **0.958**, candidate **0.792**; delta **−0.167**
  (bootstrap CI95 [−0.375, 0.000])
- Discordant pairs 6: baseline-only wins 5, candidate-only wins 1;
  one-sided McNemar p = 0.984 (improvement direction), p = 0.109
  (regression direction — short of α, hence not formally `refuted`)
- All three overtime failures were candidate arms (418s, 412s, 371s > 360s)
- Cost: candidate arms averaged **+3.3 turns (+15%)** and **+65 seconds
  (+32%)** over their baselines

The mechanism the engine's own reviews flagged as the primary risk — checklist
overhead under time budgets — is what the measurement shows: the instruction
bought no detectable correctness at a 96% baseline and converted its overhead
into overtime and near-deadline grader failures. The reviews' pre-identified
diagnostic (turn/duration deltas per arm) is exactly where the effect landed.

## Honest scope

- One model (Haiku-class subagents), one trial template, one suite, 24 pairs:
  the experiment detects large effects only, and pairs within a bundle share
  a task effect (task-level sign test reported alongside).
- `trusted_local` execution: trials ran as local subprocesses in temporary
  workspace copies; the overtime rule is enforced analytically from recorded
  durations, identically for both arms.
- The verdict is scoped to this instrument and budget. On the saturated
  single-task suites the same instruction is simply dead weight; whether it
  helps weaker models, harder-than-ceiling regimes, or laxer budgets is
  unmeasured — those are the registered next experiments in `findings.md`.

## Reproduce / extend

```bash
uv run code-scientist validate examples/measured-validation-study/state.json \
  --hypothesis hyp-a473177a6b6c \
  --intervention-file <file with the claim's instruction text> \
  --tasks benchmarks/agent-task-bundles \
  --executor host-agent --trials 3 --trial-concurrency 4 \
  --trial-timeout 360 --out <fresh dir> --dry-run
```

Drop `--dry-run` and answer the experiment's `agent-bridge` requests from a
live session (one fresh subagent per request, fixed template) to replicate.
