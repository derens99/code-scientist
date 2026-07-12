# Research Findings: Find the single appended system-prompt instruction that most improves a small headless coding agent's held-out-test pass rate on short self-contained Python implementation tasks whose prompts do not themselves instruct testing or verification. Hypotheses must be A/B-testable (baseline: no appended instruction; candidate: baseline plus exactly one instruction) and grounded in observed small-model failure modes: incomplete extraction of listed requirements, unverified edge cases, and premature completion. The agent under test already writes and runs its own ad-hoc tests when it chooses to; an intervention must add value beyond that default behavior.

Run status: completed | hypotheses: 4 | reviews: 32 | matches: 4 | evidence: 9
Hypothesis origins: generation:assumption_first_generation, generation:debate_synthesis, generation:evidence_grounded_generation, generation:failure_mode_decomposition

## Top Findings

### 1. Requirement-Checklist Extraction Instruction Raises Held-Out Pass Rate

Appending the instruction 'Before writing any code, extract every requirement stated in the task and docstrings into a numbered checklist. Before finishing, verify your implementation against each numbered item and fix any item that fails.' raises a small coding agent's held-out-test pass rate versus a no-instruction baseline on spec-dense tasks.

- Id: hyp-a473177a6b6c | Status: accepted | Elo: 1232.0 | Origin: generation:failure_mode_decomposition
- Why it matters: Targets the documented dominant failure mode (requirement omission) at its source: extraction happens before any code exists to anchor on; Produces a persistent written artifact, so compliance and extraction completeness are auditable from transcripts, unlike pure attention manipulations
- Open risks: Two-phase compliance risk: the agent may write the checklist and never perform the final per-item verification pass; Extraction quality bounds the mechanism: a checklist that misses a clause reproduces the baseline failure with extra steps
- Suggested experiment: Strongest single-arm candidate of the extraction family; transcript audit should record checklist length versus stated requirement count as a compliance measure
- Independent reviewer verdict: not yet reviewed
- Measured result: **inconclusive** (pass-rate delta -0.167, one-sided McNemar p=0.9844; experiment:exp-90368226dbba)

### 2. Adversarial Edge-Case Enumeration Instruction Raises Held-Out Pass Rate

Appending the instruction 'After implementing, act as an adversarial tester of your own code: enumerate the boundary and degenerate inputs the specification implies (empty inputs, single elements, ties, exact boundaries, invalid values, duplicates) and execute a check for each before finishing.' raises held-out pass rate versus a no-instruction baseline.

- Id: hyp-6208299229f5 | Status: accepted | Elo: 1200.0 | Origin: generation:debate_synthesis
- Why it matters: Redirects verification effort the agent already spends, so marginal overhead is low relative to test-first scaffolds; The concrete category list (empty, single, ties, boundaries, invalid, duplicates) matches where held-out graders discriminate
- Open risks: Assumes baseline failures concentrate in edge classes; if omissions are of whole requirements rather than edge handling, the redirect buys little; A fixed category list can anchor the agent and crowd out task-specific adversarial thinking
- Suggested experiment: Transcript audit of which categories the agent actually exercises would make compliance measurable alongside pass rate
- Independent reviewer verdict: not yet reviewed

## Recommended Next Experiments

- Test Requirement-Checklist Extraction Instruction Raises Held-Out Pass Rate with metrics: pass_rate, regression_count, tool_calls, wall_time, cost
- Test Adversarial Edge-Case Enumeration Instruction Raises Held-Out Pass Rate with metrics: pass_rate, regression_count, tool_calls, wall_time, cost

## Missing Evidence

- benchmark deltas
- repo-specific failure examples

## Limitations

- Elo is an internal proxy until calibrated against benchmark or human outcomes.
- benchmark deltas
- repo-specific failure examples
- Hypotheses marked with a measured result carry executed-experiment evidence scoped to that experiment's task suite and model; all other findings remain unvalidated candidates.

## Artifacts

- state.json — full run state
- report.md — comprehensive run report
- agent-packets/ — bounded subagent review packets
- agent-packets/reviews/ — independent packet-reviewer verdicts
