# Protocol Amendments

## 2026-07-12: mechanical bridge failures in verification-efficiency

Recorded and pushed before the verification-efficiency arms are rerun and
before any blinded review or coding-agent trial begins.

The first Code Scientist verification-efficiency attempt is invalid as an arm
execution. Its host responder wrote the inner JSON object directly into the
bridge wrapper's `response` field instead of serializing it as a string. The
bridge accepted the wrapper, but downstream generation could not parse those
responses and the engine persisted deterministic fallback hypotheses. This is
a transport/schema failure visible in the raw response files, not an evaluated
scientific outcome.

The first baseline verification-efficiency attempt is also invalid. After 12
valid independent proposal calls, the responder failed to notice that request
13 was a selector prompt and returned proposal-schema JSON. The runner correctly
failed on the missing selected ID. The responder then incorrectly restarted
the whole runner and answered four additional proposal calls before being
stopped, violating the registered 16-call allocation. The deleted erroneous
response cannot be reconstructed byte-for-byte; the responder's diagnostic and
the remaining request logs document the incident.

Both attempts are retained under `artifacts/invalid-attempts/` and will be
reported as incomplete in a strict no-retry sensitivity view. They are excluded
from the primary corrected execution because neither produced a protocol-valid
arm representative.

The correction is limited to rerunning the verification-efficiency objective
for both arms from empty directories with fresh responders that have not
inspected the opposing arm. All original objective text, two-cycle settings,
16-call ceiling, 4,096-token request cap, baseline 12-proposal/4-selector
allocation, rubric, and downstream rules remain unchanged. Responders must
validate that bridge `response` is a string and must read the current prompt
schema before answering. No requirement-coverage or edge-semantics arm is
rerun.

This amendment does not erase the operational defect: the final report will
present the strict original execution as `incomplete`, the corrected execution
separately, and the impact of using corrected rather than strict data.

## 2026-07-12: relative validation output invalidated

Recorded before corrected coding trials are rerun. The first three validation
experiments were launched with relative `--out` paths. The grading function
correctly runs from each isolated workspace, but the relative config path then
resolved under that workspace (for example
`workspace/studies/.../.grader-pytest.ini`) instead of pointing at the grader
config next to the workspace. Every arm consequently failed with a grader
`FileNotFoundError`; these are infrastructure failures, not task outcomes.

The three runs are retained under `artifacts/invalid-attempts/` as
`validation-relative-*`. Their reports are excluded from all primary and
sensitivity statistics. The corrected rerun uses absolute output paths and the
same registered tasks, interventions, seed, trials, timeout, and analysis.
The original arm responses remain part of the audit, and any bridge scheduling
timeouts remain failures under the same no-retry rule unless the runner itself
cannot start the grader.

## 2026-07-12: preserve executed workspaces and regrade

The absolute-path orchestration attempt was also stopped after bridge scheduling
could not answer every batch before the shared deadline; its partial files are
retained under `validation-absolute-orchestration-partial`. The executed
workspaces from the original relative-path attempt were complete and are
regraded in `artifacts/validation-final/` with absolute grader paths. This is a
grader-only replay of those already executed arms, not an agent rerun or a new
task sample. The final report separates this corrected grader result from all
strict invalid/orchestration attempts.
