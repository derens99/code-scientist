# Research Findings: Find testable ideas to improve LLM coding agents

Run status: completed | hypotheses: 6 | reviews: 18 | matches: 2 | evidence: 9
Hypothesis origins: evolution, generation, generation:assumption_decomposition, generation:research_expansion_from_meta_review

## Top Findings

### 1. Assumption audit before repo mutation

A pre-edit assumption audit that names call-path, invariant, and test-scope assumptions will reduce bad coding-agent patches.

- Id: hyp-7ede83254dda | Status: accepted | Elo: 1200.0 | Origin: generation:assumption_decomposition
- Why it matters: structured hypothesis; explicit assumptions
- Open risks: needs measured benchmark evidence before claiming improvement
- Suggested experiment: No retrieved safety-boundary evidence found for safety exploration.
- Independent reviewer verdict: not yet reviewed

### 2. Tournament-ranked prompt variants

Pairwise tournament ranking of prompt variants will identify more reliable coding-agent workflows than single-prompt selection.

- Id: hyp-37f693681af3 | Status: accepted | Elo: 1200.0 | Origin: generation
- Why it matters: structured hypothesis; explicit assumptions
- Open risks: needs measured benchmark evidence before claiming improvement
- Suggested experiment: No retrieved safety-boundary evidence found for safety exploration.
- Independent reviewer verdict: not yet reviewed

## Recommended Next Experiments

- Test Assumption audit before repo mutation with metrics: pass_rate, regression_count, tool_calls, wall_time, cost
- Test Tournament-ranked prompt variants with metrics: pass_rate, regression_count, tool_calls, wall_time, cost

## Missing Evidence

- benchmark deltas
- repo-specific failure examples

## Limitations

- Elo is an internal proxy until calibrated against benchmark or human outcomes.
- benchmark deltas
- repo-specific failure examples

## Artifacts

- state.json — full run state
- report.md — comprehensive run report
- agent-packets/ — bounded subagent review packets
- agent-packets/reviews/ — independent packet-reviewer verdicts
