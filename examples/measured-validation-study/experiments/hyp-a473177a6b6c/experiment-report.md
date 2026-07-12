# Experiment Report: Requirement-Checklist Extraction Instruction Raises Held-Out Pass Rate

- Experiment: `exp-90368226dbba` (protocol sha256 `9f6c2ee38a255d4cfc3613f20263cf65264b4e4514fb12f60017ff2e28e951a3`)
- Hypothesis: `hyp-a473177a6b6c` — Appending the instruction 'Before writing any code, extract every requirement stated in the task and docstrings into a numbered checklist. Before finishing, verify your implementation against each numbered item and fix any item that fails.' raises a small coding agent's held-out-test pass rate versus a no-instruction baseline on spec-dense tasks.
- Executor: host-agent (model `claude-haiku-4-5`, max 15 turns, auth login)
- Tasks: 8 × 3 paired trials, seed 20260712
- Status: **complete**, verdict: **inconclusive**
- Total measured cost: $0.00 (budget $10.00)

## Intervention (candidate arm `--append-system-prompt`)

```
Before writing any code, extract every requirement stated in the task and docstrings into a numbered checklist. Before finishing, verify your implementation against each numbered item and fix any item that fails.
```

Baseline: Agent defaults: identical prompt, model, tools, and limits with no appended system prompt.

## Outcomes By Task

| Task | Baseline passes | Candidate passes |
| --- | --- | --- |
| bundle-01 | 2/3 | 2/3 |
| bundle-02 | 3/3 | 3/3 |
| bundle-03 | 3/3 | 3/3 |
| bundle-04 | 3/3 | 3/3 |
| bundle-05 | 3/3 | 2/3 |
| bundle-06 | 3/3 | 1/3 |
| bundle-07 | 3/3 | 2/3 |
| bundle-08 | 3/3 | 3/3 |

## Statistics

- Pairs: 24 (baseline pass rate 0.958, candidate 0.792)
- Pass-rate delta: -0.167 (bootstrap CI95 [-0.375, +0.000])
- Discordant pairs: 6 (candidate-only wins 1, baseline-only wins 5)
- Primary (pre-registered): one-sided exact McNemar p = 0.9844 at alpha 0.05 with minimum 3 discordant pairs
- Robustness: task-level sign test p = 1.0000 (0 tasks better, 3 worse, 5 tied)

## Caveats

- Pairs within a task share a task effect; the pair-level McNemar test is mildly anticonservative under clustering. The task-level sign test is the robustness check.
- Execution policy is trusted_local: trials ran as local subprocesses in temporary workspace copies with no sandbox-isolation claim.
- Results are specific to the task suite, model, and turn/timeout limits registered in the protocol; they do not establish generality beyond them.
