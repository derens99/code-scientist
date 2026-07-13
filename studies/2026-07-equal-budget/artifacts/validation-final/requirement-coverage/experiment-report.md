# Experiment Report: Coverage-First Round-Robin Passes

- Experiment: `exp-3bd22df91276` (protocol sha256 `33c27b1a0e70dfbade13057d4d0edd3d73c8bdf20ee0fecb255e95091deb806d`)
- Hypothesis: `hyp-cb75262aba7b` — Appending exactly this instruction — 'Use round-robin coverage passes: first remove every stub and implement the smallest specification-valid path in every module; only then revisit modules in descending risk to add boundary and error clauses, never polishing one module while another required behavior remains wholly unimplemented.' — will increase all-modules held-out pass rate under a fixed deadline relative to no appended instruction.
- Executor: host-agent (model `claude-haiku-4-5`, max 15 turns, auth login)
- Tasks: 4 × 2 paired trials, seed 20260712
- Status: **complete**, verdict: **inconclusive**
- Total measured cost: $0.00 (budget $10.00)

## Intervention (candidate arm `--append-system-prompt`)

```
Use round-robin coverage passes: first remove every stub and implement the smallest specification-valid path in every module; only then revisit modules in descending risk to add boundary and error clauses, never polishing one module while another required behavior remains wholly unimplemented.
```

Baseline: Agent defaults: identical prompt, model, tools, and limits with no appended system prompt.

## Outcomes By Task

| Task | Baseline passes | Candidate passes |
| --- | --- | --- |
| bundle-05 | 2/2 | 2/2 |
| bundle-06 | 2/2 | 2/2 |
| bundle-07 | 2/2 | 2/2 |
| bundle-08 | 2/2 | 2/2 |

## Statistics

- Pairs: 8 (baseline pass rate 1.000, candidate 1.000)
- Pass-rate delta: +0.000 (bootstrap CI95 [+0.000, +0.000])
- Discordant pairs: 0 (candidate-only wins 0, baseline-only wins 0)
- Primary (pre-registered): one-sided exact McNemar p = 1.0000 at alpha 0.05 with minimum 3 discordant pairs
- Robustness: task-level sign test p = 1.0000 (0 tasks better, 0 worse, 4 tied)

## Caveats

- Pairs within a task share a task effect; the pair-level McNemar test is mildly anticonservative under clustering. The task-level sign test is the robustness check.
- Execution policy is trusted_local: trials ran as local subprocesses in temporary workspace copies with no sandbox-isolation claim.
- Results are specific to the task suite, model, and turn/timeout limits registered in the protocol; they do not establish generality beyond them.

## Notes

- Regraded from executed workspaces after relative grader-path infrastructure failure.
- No agent was rerun; absolute final artifact paths were used for this grader pass.
