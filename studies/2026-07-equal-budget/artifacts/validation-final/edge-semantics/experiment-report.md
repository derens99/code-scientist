# Experiment Report: Boundary-contract precommitment

- Experiment: `exp-4fc659db9869` (protocol sha256 `07db29ce11b2bb4e1b2ac96ebee33fdc2aae84f436583c41a307f1d783c16a70`)
- Hypothesis: `hyp-4e43c9afce38` — Appending exactly this instruction—"Before editing code, write a compact boundary contract for every affected callable that lists valid-domain edges, invalid-input behavior, and the exact exception type and message, then make the implementation and tests conform to that contract."—may increase held-out boundary and error-semantics pass_rate, relative to no appended instruction, when otherwise identical coding agents receive equal tool-call and wall-time caps across several Python modules.
- Executor: host-agent (model `claude-haiku-4-5`, max 15 turns, auth login)
- Tasks: 4 × 2 paired trials, seed 20260712
- Status: **complete**, verdict: **inconclusive**
- Total measured cost: $0.00 (budget $10.00)

## Intervention (candidate arm `--append-system-prompt`)

```
Before editing code, write a compact boundary contract for every affected callable that lists valid-domain edges, invalid-input behavior, and the exact exception type and message, then make the implementation and tests conform to that contract.
```

Baseline: Agent defaults: identical prompt, model, tools, and limits with no appended system prompt.

## Outcomes By Task

| Task | Baseline passes | Candidate passes |
| --- | --- | --- |
| bundle-05 | 2/2 | 2/2 |
| bundle-06 | 2/2 | 1/2 |
| bundle-07 | 2/2 | 1/2 |
| bundle-08 | 0/2 | 0/2 |

## Statistics

- Pairs: 8 (baseline pass rate 0.750, candidate 0.500)
- Pass-rate delta: -0.250 (bootstrap CI95 [-0.625, +0.000])
- Discordant pairs: 2 (candidate-only wins 0, baseline-only wins 2)
- Primary (pre-registered): one-sided exact McNemar p = 1.0000 at alpha 0.05 with minimum 3 discordant pairs
- Robustness: task-level sign test p = 1.0000 (0 tasks better, 2 worse, 2 tied)

## Caveats

- Pairs within a task share a task effect; the pair-level McNemar test is mildly anticonservative under clustering. The task-level sign test is the robustness check.
- Execution policy is trusted_local: trials ran as local subprocesses in temporary workspace copies with no sandbox-isolation claim.
- Results are specific to the task suite, model, and turn/timeout limits registered in the protocol; they do not establish generality beyond them.

## Notes

- Regraded from executed workspaces after relative grader-path infrastructure failure.
- No agent was rerun; absolute final artifact paths were used for this grader pass.
