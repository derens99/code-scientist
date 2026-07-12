# Agent Tasks — No-Harness Variant

Generated from [benchmarks/agent-tasks](../agent-tasks) with two mechanical changes:

1. `tests_visible/` is removed from every workspace.
2. The single prompt sentence instructing the agent to run the visible tests
   ("Run `python -m pytest tests_visible -q` to check your work; …") is removed.
   Nothing else in any prompt changes; specifications remain complete in the
   prompt bodies and docstrings. Graders and reference solutions are identical
   to the source suite.

## Why this variant exists

Calibration on the source suite (2026-07-12, one baseline probe per task,
Haiku subagent trials) measured a 10/10 baseline pass rate: with a visible
test suite and an explicit instruction to run it, the baseline agent already
performs the verification behavior that prompt-level interventions try to
induce, so the instrument has no headroom and every paired experiment would
come out inconclusive by construction.

This variant removes the built-in verification harness from the *instrument*
so the baseline is a plain agent given code and a specification. Interventions
that add checking/verification behavior have room to show an effect here —
and room to be refuted. Held-out grading is unchanged, so pass/fail means the
same thing in both suites.

Results measured on this variant are scoped to it: they say what an added
instruction does when the task setup does not already demand verification,
not what it does on top of an existing test-running workflow (the source
suite measures that regime, where the baseline is at/near ceiling for this
model).

Regenerate after editing the source suite: copy each task, drop
`tests_visible/`, strip prompt sentences matching `tests_visible|visible
tests`, and confirm no spec content was removed.
