# Deep Verification Review Traces

## Goal

Move the deterministic reflection path closer to the paper's multi-turn scientific worker behavior by preserving the verification loop used by `deep_verification` reviews.

## Scope

- Add a backward-compatible `Review.review_trace` field.
- Make deterministic `deep_verification` perform and record multiple evidence-query turns.
- Render review traces in markdown reports and the workbench hypothesis detail view.
- Update the paper gap analysis to describe the completed slice and remaining work.

## Verification

- Add unit tests for review trace round-tripping and deep verification trace content.
- Add report and UI rendering tests.
- Run focused Python and frontend tests before the full verification suite.
