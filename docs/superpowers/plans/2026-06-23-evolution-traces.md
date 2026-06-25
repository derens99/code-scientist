# Evolution Traces

## Goal

Move strategy-specific evolution closer to the paper's inspectable scientific worker loops by preserving the evidence and feedback queries used to derive evolved hypotheses.

## Scope

- Add a backward-compatible `Hypothesis.evolution_trace` field.
- Record deterministic evolution turns for parent mechanisms, feedback constraints, and strategy grounding.
- Render evolution traces in markdown reports and the workbench hypothesis detail view.
- Update the paper gap analysis and verification counts.

## Verification

- Add model round-trip and old-state default tests.
- Add agent behavior tests for strategy evolution traces.
- Add report and workbench rendering tests.
- Rerun focused checks, then the full Python and frontend verification suite.
