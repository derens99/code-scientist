# Codebase Audit — 2026-07-12

Seven parallel read-only subsystem reviewers plus an owner hazard sweep, every
reported finding personally verified at the cited code before action. The fixed
set includes the v0.1.0 hardening release with regression tests (524 Python +
38 web tests green). Remaining items are ranked recommendations that still need
a design decision or a larger, separately-tested change.

## Fixed (committed, tested)

| # | Sev | Area | Defect | Commit |
|---|-----|------|--------|--------|
| F1 | Critical | supervisor Elo | Ranking loop scored each pair from stale schedule-time snapshots; a hypothesis in >1 pair/cycle lost its earlier Elo delta (reproduced: 1406 vs correct 1420). | dccf09d |
| F2 | High | agent_packets | `select_top_hypotheses` filtered only `merged_duplicate`, so safety-quarantined / rejected hypotheses reached subagent work packets. Unified `INACTIVE_STATUSES` in models. | dccf09d |
| F3 | High | experiments | Overtime rule never fired for the host-agent executor it exists for (synthesized timeout `duration == budget` vs strict `>`). | 8a5dfba |
| F4 | High | experiments | Deterministic request ids + never-purged `responses/` → crash-then-rerun replayed stale bridge answers as fabricated measurements. Bridge purged at start. | 8a5dfba |
| F5 | High | experiments | `grade_workspace` executed agent-writable pytest config (workspace `conftest.py` skip-all, `pyproject` addopts, ancestor repo config) → false PASS. Now pins isolated config, `--rootdir`, `--noconftest`, strips `PYTEST_*`. | 8a5dfba |
| F6 | High | tools/evidence | `is_file()` follows symlinks; a link inside a scanned repo/corpus (`repo/x.txt -> /etc/passwd`) was read into evidence. Recursion now requires resolved target within root. | 2316767 |
| F7 | Medium | tools | Server-supplied unknown charset raised `LookupError` from `decode()` and aborted researcher collectors. Validated via `codecs.lookup`, utf-8 fallback. | 8a5dfba |
| F8 | Medium | llm bridge | Response reader caught `JSONDecodeError` but not the `UnicodeDecodeError` a partial multibyte write raises → poll-loop crash. Broadened to `ValueError`. | 8a5dfba |
| F9 | Medium | llm bridge | Fence stripper ate single-line ` ```json{...}``` ` payloads whole and kept trailing prose. Rewritten. | 8a5dfba |
| F10 | Low | reporting | `_reviewer_verdict` read the packet's option-enumeration template line as verdict "keep". Now ignores enumeration lines. | dccf09d |
| F11 | Low | experiments | Task-authored timeout silently clamped by protocol default (bundles 360→300). Now warns. | 8a5dfba |
| F12 | High | state persistence | CLI and workbench mutations could tear or clobber `state.json`. Python and Node now share an exclusive lock-file protocol, reload after locking, and atomically replace state. | v0.1.0 hardening |
| F13 | High | scheduler | Ranking could run before proximity deduplication. Ranking now has an explicit dependency on the cycle's proximity task. | v0.1.0 hardening |
| F14 | High | task lifecycle | A terminal single-concurrency task failure could escape before persistence. The failed queue is now persisted before re-raising. | v0.1.0 hardening |
| F15 | Medium | provider coordination | Stale snapshots could regress terminal coordinator rows and interrupted provider reviews could replay. Terminal rows now win reconciliation, provider interruptions fail closed, and worker processes are reaped in `finally`. | v0.1.0 hardening |
| F16 | Med-High | workbench | Path and direct-fetch inputs were unconfined. Paths now require configured roots and fetches require HTTPS plus an explicit domain allowlist. | v0.1.0 hardening |
| F17 | Medium | workbench | Mutating routes lacked browser-origin checks. They now reject cross-site/mismatched-origin requests and the server binds to loopback by default. | v0.1.0 hardening |

## Remaining recommendations

These need a design decision or a larger change with its own test plan.

- **R4 [Medium] Forward-compat loads crash with a context-free `TypeError`.**
  Every `cls(**data)` `from_dict` breaks on a state written by a newer build
  (unknown field) with no hint of which record/file. Also `TestPlan`,
  `EloTrajectoryPoint`, `SafetyDecision` lack the tolerant `setdefault` scaffold
  the backward-compat guarantee relies on. Fix: filter to known fields (stash or
  re-raise as a clear `ValueError` naming the field/record); add the scaffold to
  the three unguarded models. (All 49 committed states currently round-trip
  losslessly — this is forward/latent, not an active break.)

- **R6 [Medium] Env leakage into CLI children.** `ClaudeCLIClient` denylists
  only 3 Anthropic vars, inheriting all other host secrets into the spawned
  `claude`; the codex path passes `env=None` (full env incl. the proxy vars).
  Fix: allowlist the child env. (Left unfixed to avoid breaking working setups
  that rely on inherited proxy/config vars — needs the allowlist scoped
  carefully.)

- **R7 [Medium] Safety evidence-screen injection + index trust.** Untrusted
  evidence content is interpolated into the critic prompt with a forgeable
  `--- subject N ---` delimiter, and batch verdicts are keyed by the model's
  self-reported `index` (duplicate/offset indices silently misattribute
  verdicts). Structural mitigation exists (deterministic deny is final; only
  allowed items reach the model — injection can only *loosen*). Fix: nonce-fence
  or JSON-encode subjects; require a contiguous 1..N index set.

## Web workbench (separate surface)

R8 and R9 are resolved in the v0.1.0 hardening release. Remaining lower-priority
items: error responses leak absolute host paths / engine tracebacks; objective
passed as a bare positional (objectives starting with `-` silently break — add
`--`); unbounded `state.json` reads; fixed-rate polling with no backoff.

## Structural / cleanup (low urgency)

- Dead code: `pick_next_task` (tests-only), `coordination.acquire_named_lease`
  (no callers), `claim(eligible_kinds=…)` (never passed), a dead
  `_build_model_client` fallback in `_build_generation_agent` that would bypass
  the budget cap if reached.
- Duplication: `_hypothesis_text` drifted between `benchmarks.py` and
  `evaluation.py` (different field sets → term selectors match in one context,
  silently miss in the other); `_pick_next_tasks` vs `select_scheduler_task_pool`
  duplicate the selection loop; review-validation triplicated.
- `supervisor.py` (4.7k lines) / `agents.py` (4.9k lines) with 1.4k-line
  `run_research_cycle` and 800-line `cli.main` are maintenance liabilities;
  extract cohesive units opportunistically.
- Persist path is O(total history) per call (re-reads ledger, rewrites all
  transcripts, re-upserts the never-pruned task queue) → continuous runs degrade
  quadratically. Prune completed tasks from old cycles; track ledgered event ids
  in memory.

## Explicitly rejected (checked, not bugs)

Elo simultaneous-update math (zero-sum verified), budget off-by-one, argv
injection (all providers pass prompts via stdin), `atomic_write_json` writer-
side atomicity, thread-local drain-buffer correctness (wave-2), the stats math
in experiments (McNemar/bootstrap/verdict boundaries probed exhaustively),
XSS in the web client (React auto-escapes; no `dangerouslySetInnerHTML`),
server-side host-agent provider rejection, and network timeouts (all present).
