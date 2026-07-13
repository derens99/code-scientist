# Experiment Report: Cross-module counterexample first

- Experiment: `exp-e8940cd44e68` (protocol sha256 `d0e7445e06b80ca63aafc001ac8b725aa267c53ef536cc37cde4ac5ca3448342`)
- Hypothesis: `hyp-96ae9555347a` — Appending exactly this one system-prompt instruction—"Before broad verification of a multi-module Python change, identify the most plausible silent contract violation at a changed module boundary, run the cheapest check capable of falsifying that contract first, then use only the remaining pre-deadline verification budget on broader checks."—will, versus no appended instruction with all other conditions fixed, reduce regression_count without increasing deadline misses; pass_rate, tool_calls, wall_time, and cost will be measured to determine whether the tradeoff is favorable.
- Executor: host-agent (model `claude-haiku-4-5`, max 15 turns, auth login)
- Tasks: 4 × 2 paired trials, seed 20260712
- Status: **complete**, verdict: **inconclusive**
- Total measured cost: $0.00 (budget $10.00)

## Intervention (candidate arm `--append-system-prompt`)

```
Before broad verification of a multi-module Python change, identify the most plausible silent contract violation at a changed module boundary, run the cheapest check capable of falsifying that contract first, then use only the remaining pre-deadline verification budget on broader checks.
```

Baseline: Agent defaults: identical prompt, model, tools, and limits with no appended system prompt.

## Outcomes By Task

| Task | Baseline passes | Candidate passes |
| --- | --- | --- |
| bundle-05 | 2/2 | 2/2 |
| bundle-06 | 1/2 | 1/2 |
| bundle-07 | 2/2 | 2/2 |
| bundle-08 | 0/2 | 0/2 |

## Statistics

- Pairs: 8 (baseline pass rate 0.625, candidate 0.625)
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
