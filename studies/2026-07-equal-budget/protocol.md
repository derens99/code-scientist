# Pre-registration: Equal-Budget Code Scientist Comparison

Registered: 2026-07-12, America/New_York, before any arm execution.

## Question and scope

Does Code Scientist's multi-stage research loop produce better prompt-level
coding-agent interventions than a strong best-of-N collection of independent
single-shot proposals when both arms use the same host model, realized model
call count, and requested output-token cap?

This is prospective external-to-engine validation with model reviewers and
local coding-agent trials. It is not a human study and cannot establish human
preference, cross-model generalization, or production effectiveness.

## Objectives

The registered objectives are in `study-manifest.json`:

1. requirement coverage under multi-module time pressure;
2. edge-case and error-semantics correctness;
3. verification efficiency without deadline regressions.

Every proposal must be exactly one appended system-prompt intervention that can
be tested against a no-intervention baseline.

## Arms and equal budget

Both arms use the same live Codex host-agent session and request
`max_tokens=4096` for every completion. Code Scientist runs two cycles with a
ceiling of three hypotheses, one ranking match per cycle, and a hard ceiling of
16 host-model calls per objective.

For each objective, let `N` be Code Scientist's realized count of answered
host-model bridge requests. The comparison baseline receives exactly `N`
answered requests. If `N < 8`, that objective is incomplete and excluded from
the across-objective success rule without replacement.

The baseline is best-of-N single-shot:

- `S = N - max(2, floor(N/4))` independent calls each produce one proposal
  directly from the objective, without seeing other calls or Code Scientist
  output;
- the remaining calls independently select the strongest proposal from the
  same anonymized set using the registered rubric;
- plurality selection chooses the baseline representative; ties break by the
  lowest stable proposal digest.

No baseline call receives retrieved evidence, intermediate critiques, rankings,
or another baseline call's prose except the final selection calls. This is a
strong best-of-N single-shot baseline, not the repository's canned deterministic
baseline scaffold.

The final report will disclose actual request counts and response character
counts. The host bridge does not expose token telemetry, so equality is claimed
for call counts and requested caps, not measured token consumption.

## Blinded model review

Three fresh independent reviewer subagents each receive all three arm pairs.
Arm labels and internal IDs are removed and randomized independently per
reviewer. Reviewers do not receive the answer key, engine traces, rankings, or
coding-trial outcomes. Each reviewer returns:

- a forced preference (`arm_a`, `arm_b`, or `no_preference`);
- 1-5 scores for specificity, plausibility, testability, mechanism clarity,
  risk awareness, and protocol quality;
- a short justification and confidence.

The review packet is frozen before reviewers start. The answer key is revealed
only after all three returned files exist.

Primary ideation endpoint: Code Scientist wins at least 6 of the 9
reviewer-objective judgments, counting `no_preference` as half a win for each
arm, and has a positive mean total-rubric-score difference. Otherwise the
ideation result is `inconclusive`; it is `refuted` only if the symmetric
baseline threshold is met. These small-sample results are descriptive, not a
population significance claim.

## Prospective coding-agent validation

The selected proposal from each arm pair is not used directly as the coding
treatment. To test the Code Scientist workflow's downstream value, the
Code Scientist representative for each objective is converted mechanically to
the single imperative intervention stated in its claim. If no single imperative
can be extracted without interpretation, that objective is incomplete.

Each of the three registered Code Scientist interventions is tested with
`code-scientist validate` on bundles 05-08 from
`benchmarks/agent-task-bundles`, two paired trials per bundle, seed 20260712,
360-second arm timeout, and identical host-agent trial templates. This yields
3 × 4 × 2 = 24 registered pairs / 48 arms. The task files, hidden graders, and
workspace contents are withheld from proposal generation and blind review.

The coding endpoint pools the registered objective × bundle × trial pairs as a
portfolio test of the workflow. Primary analysis is a one-sided exact McNemar
test at alpha 0.05 with at least three discordant pairs. A positive pass-rate
delta and p < 0.05 is `supported`; the symmetric significant negative result is
`refuted`; all other completed outcomes are `inconclusive`. Bootstrap delta
intervals and objective-, task-, duration-, and turn-level breakdowns are
secondary diagnostics. Timeout is failure. Only a documented infrastructure
failure before agent workspace mutation may be retried, using the same arm and
seed.

## Overall decision and stopping

The overall claim is `supported` only if both the ideation and downstream
coding endpoints are supported. It is `refuted` if either endpoint meets its
registered symmetric refutation rule. Otherwise it is `inconclusive` (or
`incomplete` when execution/coverage rules fail).

Execution stops after the registered budgets and 24 pairs. No extra objective,
reviewer, task, trial, or alternate intervention may be added after observing
outcomes. Infrastructure or protocol amendments must be appended, timestamped,
and committed before the affected phase resumes; the original rule remains
visible.

## Artifact and audit requirements

The committed result must include arm states, bridge response logs, anonymous
review packets, reviewer returns, the post-review answer key, validation
protocols/results, aggregation code or commands, environment versions, git
commit, exclusions/retries, and an honest final report. Generated hypotheses
remain hypotheses until prospective measurements support them.
