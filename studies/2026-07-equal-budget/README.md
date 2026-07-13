# Equal-Budget Prospective Comparison

This directory contains the pre-registration, runner inputs, and eventually the
complete artifacts for a prospective comparison of Code Scientist against a
strong best-of-N single-shot baseline. The protocol was committed and pushed
before either arm was executed.

The study is intentionally scoped as model and coding-agent evidence. Its blind
reviewers are independent Codex subagents, not humans, and the held-out tasks
are local public benchmark bundles. The final report must retain those limits.

Registered files:

- `protocol.md`: hypotheses, budgets, outcomes, analysis, and stopping rules.
- `study-manifest.json`: the three research objectives supplied to Code Scientist.
- `run_baseline.py`: auditable host-agent bridge runner for the matched-call baseline.

Generated outcomes will be added only after execution under `artifacts/`.
