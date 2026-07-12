# Measured Validation Design (2026-07-12)

## Motivation

Every prior evidence channel is either asserted (benchmark fixtures, evaluation
returns) or a proxy (reviews, Elo). The paper's co-scientist earned its result
with prospective wet-lab validation; the coding-domain equivalent is executing
a hypothesis as a controlled experiment on a real coding agent and measuring
the outcome. This wave adds that: a pre-registered, paired, baseline-vs-candidate
experiment runner whose subject is a headless coding agent (`claude -p`) solving
held-out-graded tasks, producing a `BenchmarkResult` whose provenance is
`measured` rather than `fixture`.

## Non-Goals

- No sandbox-isolation claims: execution policy is `trusted_local`, same honesty
  contract as `prospective-validation-run`. Hardened isolation stays refused.
- No automatic intervention synthesis: the operator (or host agent) supplies the
  candidate intervention text derived from the hypothesis; the protocol records
  it verbatim before anything runs.
- No external benchmark suites (SWE-bench et al.); the committed task suite is
  small, original, stdlib-only, and fast.
- Statistics stay honest at small n: exact tests plus explicit inconclusive
  verdicts, never point-estimate victory laps.

## Task Suite Format

`benchmarks/agent-tasks/<task-id>/`:

- `task.json` — `{"id", "title", "prompt", "timeout_seconds"?}`. `prompt` is the
  complete instruction the agent receives.
- `workspace/` — starter files copied into a fresh trial directory. May include
  visible tests the agent can run.
- `grader/` — held-out pytest files. Never present while the agent runs; copied
  in afterwards and executed with the engine's interpreter. Task passes iff
  pytest exits 0.

Grader tests are a superset of visible behavior: passing visible tests must not
guarantee passing the grader, otherwise the metric saturates.

## Experiment Protocol (Pre-Registration)

`ExperimentProtocol` is written to `protocol.json` in the experiment directory
before the first trial and hashed (sha256 of canonical JSON); results embed the
hash so a result can always be checked against what was registered. Fields:

- experiment id, created_at, state path, hypothesis id/title/claim
- `baseline`: description (agent defaults, no appended prompt)
- `intervention`: exact `--append-system-prompt` text for the candidate arm
- task ids, trials per task, seed (drives arm-order interleaving)
- executor kind, model id, max turns, per-trial timeout, allowed/disallowed tools
- decision rule: alpha, direction (one-sided candidate>baseline), minimum
  discordant pairs
- cost budget USD (hard stop)

## Executors

Common interface: run one trial arm in a prepared workspace, return outcome +
metrics (`duration_seconds`, `num_turns`, `cost_usd`, raw transcript path).

- `deterministic` — test/demo executor; a scripted table maps
  (task, arm) → applied patch or no-op. Offline, no network, exercises the whole
  pipeline including grading and stats. Labeled scaffolding, like every other
  deterministic path.
- `claude-cli` — headless Claude Code: `claude -p <prompt> --output-format json
  --model <id> --max-turns <n> [--append-system-prompt <intervention>]` with
  cwd = trial workspace. Auth modes:
  - `login` (default): strip `ANTHROPIC_API_KEY/AUTH_TOKEN/BASE_URL` from the
    child env (existing gotcha), reuse local CLI login.
  - `api-key`: require a key from the env file and pass it explicitly; used when
    the CLI login is unavailable. Recorded in the protocol.
  Binary resolution reuses `llm.py`'s fallback (`~/.claude/local/claude`).

## Trial Procedure

For each (task, trial-index) pair, both arms run with identical inputs except
the intervention:

1. Arm order comes from a seeded RNG (interleaved, not all-baseline-then-all-candidate).
2. Fresh workspace: copy `workspace/` into `trials/<task>/<n>/<arm>/workspace`.
3. Run the executor with the task prompt (per-trial timeout; timeout = fail).
4. Copy `grader/` in, run pytest with the engine interpreter, record pass/fail
   and the pytest tail.
5. Persist provenance: agent stdout JSON, workspace diff, grader output.
6. After every trial, add up reported `cost_usd`; if the budget is exceeded the
   experiment stops and reports `incomplete` (never silently truncates).

## Statistics And Verdict

Primary (pre-registered): pair-level exact McNemar. Pairs are (task, trial)
with binary outcomes; among discordant pairs, one-sided binomial test that
candidate wins exceed baseline wins. Verdict:

- `supported` — p < alpha and pass-rate delta > 0
- `refuted` — opposite direction at alpha
- `inconclusive` — otherwise, or fewer discordant pairs than the registered
  minimum

Secondary (robustness, reported not decided on): task-level sign test over
per-task trial-win aggregates, since pairs within a task share a task effect
and pair-level McNemar is mildly anticonservative under clustering. The report
states this caveat. Bootstrap (seeded, pairs resampled) gives a 95% CI on the
pass-rate delta. Wall time, turns, and cost get descriptive deltas only.

## State Integration

`BenchmarkResult` gains backward-compatible optional fields (defaults preserve
old `state.json` loading):

- `provenance: str = ""` — `"measured:agent-experiment"` for this path; empty
  means legacy/fixture
- `hypothesis_id: str = ""`
- `verdict: str = ""` — supported/refuted/inconclusive/incomplete
- `stats: dict[str, float] = {}` — p-value, CI bounds, pair counts

Metric mapping keeps the required benchmark shape: `pass_rate` (trial mean),
`regression_count` (pairs baseline-pass → candidate-fail), `tool_calls`
(mean turns), `wall_time` (mean seconds), `cost` (arm total USD).

The `validate` CLI appends the result to the run's `state.json` (tolerant
load → append → save), writes `experiment.json` + `experiment-report.md` under
`<run>/experiments/<experiment-id>/`, and `report`/`findings` render measured
results with their verdict and provenance, distinguished from fixtures.

## CLI Surface

```
code-scientist validate <state_json>
  --hypothesis <id>
  --intervention-file <path> | --intervention "<text>"
  --tasks benchmarks/agent-tasks
  --task <id> (repeatable; default all)
  --executor deterministic|claude-cli
  --trials 3 --seed 7
  --model <model-id> --max-turns 15 --trial-timeout 300
  --agent-auth login|api-key --env-file .env
  --cost-budget-usd 10
  --alpha 0.05 --min-discordant 3
  --out <dir> (default <run>/experiments/<experiment-id>)
  --dry-run (pre-register only)
```

## Testing

- Stats: known-answer McNemar/sign/bootstrap cases, verdict boundaries.
- Grading: pass and fail workspaces, grader isolation (grader absent during the
  agent phase), timeout handling.
- Deterministic executor: full experiment end-to-end offline, interleaving
  determinism under a fixed seed, budget stop.
- claude-cli executor: fake `claude` binary on PATH (existing test pattern),
  auth-mode env handling both directions, JSON parse failures.
- Protocol: pre-registration happens before execution, hash stability,
  `--dry-run`.
- Backward compat: old `BenchmarkResult` dicts without new fields still load.
