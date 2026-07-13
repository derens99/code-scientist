# Code Scientist Capability Study

- Runs: 3
- Baseline evaluations: 0
- Baseline win rate: 0.000
- Mean score delta: +0
- Score delta sample count: 0
- Score delta 95% CI: [+0, +0]
- Score delta effect size: 0.000
- Baseline win sign-test p-value: 1.000
- Mean Elo-human correlation: 0.000
- Mean Elo-benchmark correlation: 0.000
- Scaling points: 0
- Scaling delta trend: +0
- Prospective records: 0
- Prospective success rate: 0.000
- Feedback-loop measurements: 0
- Feedback-loop positive rate: 0.000
- Feedback-loop mean delta: +0
- Feedback-loop metric deltas: none
- Summary: Capability study summary over 0 baseline evaluations: win rate 0.000, mean score delta +0.000; scaling delta trend +0.000; prospective success rate 0.000; feedback-loop positive rate 0.000.

## Study Coverage Audit

- Status: incomplete
- Unique goals: 3
- Baselines: none
- Capability evaluations: 0
- Human-scored candidates: 0
- Human rubric judgments: 0
- Human preference judgments: 0
- Benchmark-scored candidates: 0
- Benchmark result artifacts: 0
- Scaling points: 0
- Prospective/external measurements: 0
- Feedback-loop measurements: 0
- Safety evaluations: 0
- Elo concordance results: 0
- Elo trajectory points: 3
- Missing requirements: baseline workflow comparisons, human rubric scores, criterion-level human rubric judgments, human preference judgments, benchmark scores or benchmark result artifacts, test-time compute scaling curve, prospective/external validation measurements, external feedback-loop measurement, safety red-team evaluation
- Summary: Study coverage is incomplete; missing baseline workflow comparisons, human rubric scores, criterion-level human rubric judgments, human preference judgments, benchmark scores or benchmark result artifacts, test-time compute scaling curve, prospective/external validation measurements, external feedback-loop measurement, safety red-team evaluation.

## Included Goals

- Identify exactly one appended system-prompt instruction that could improve a coding agent's complete extraction and implementation of dispersed requirements across several Python modules under a fixed deadline. The intervention must be directly A/B testable against no appended instruction, add minimal overhead, name its causal mechanism, and state concrete failure risks.
- Identify exactly one appended system-prompt instruction that could improve a coding agent's correctness on boundary cases, invalid-input behavior, and exact error semantics across several Python modules under a fixed deadline. The intervention must be directly A/B testable against no appended instruction, avoid generic advice, name its causal mechanism, and state concrete failure risks.
- Identify exactly one appended system-prompt instruction that could improve a coding agent's verification efficiency on multi-module Python tasks: catch correctness failures without increasing deadline misses. The intervention must be directly A/B testable against no appended instruction, specify how verification effort is prioritized, name its causal mechanism, and state concrete failure risks.

## Component Ablation Readout

- No complete paired ablation arms found.
- Proximity-vs-review-quality-difference correlation: -1.000 across 2 runs
  - This is a review-score proxy; replace it with independent expert quality scores for a paper-level result.
