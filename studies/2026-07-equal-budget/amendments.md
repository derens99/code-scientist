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
