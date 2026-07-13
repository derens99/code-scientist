# Equal-Budget Prospective Comparison

Overall verdict: **refuted** under the pre-registered endpoint rule.

The three blinded independent model reviewers preferred the best-of-N single-shot baseline in all 9 judgments; its mean total rubric score exceeded Code Scientist's. The coding endpoint was inconclusive: requirement coverage tied 8/8 pairs, edge semantics favored baseline 6/8 vs 4/8, and verification efficiency tied 5/8. Pooled pass rates were 19/24 baseline and 17/24 candidate (delta -0.0833), but only two discordant pairs, below the registered minimum of three.

The raw attempts with invalid bridge wrappers, relative grader paths, and orchestration timeouts are retained under `artifacts/invalid-attempts/` and excluded from the primary result. The absolute-path regrade used the already executed workspaces and the same hidden grader tests; it did not rerun agents.

This is model-review and local coding-agent evidence, not human validation or production evidence.
