# Agent Benchmark Task Suite — Hard

This directory holds a **de-saturated** sibling of `benchmarks/agent-tasks/`
(and its no-harness variant), calibrated for a competent small-model coding
agent that reads a spec once and tests what it thinks of. Same
pass/fail contract as the other suites: an agent works in a copy of
`workspace/`, then a held-out grader is copied into the workspace root and
`python -m pytest -q` is run from there. A task **passes** iff that command
exits 0.

## Difficulty philosophy

The source suite measured 10/10 on a Haiku-class baseline: each task's
requirement set was small enough for the agent to hold in mind after one
read, so the instrument had no headroom. This suite targets a **~30-70%**
pass rate for the same class of agent, achieved through **requirement
breadth, never ambiguity or trick puzzles**:

- Every task's prompt + docstring states **10-15 independently testable
  behaviors** up front — boundary semantics (inclusive/exclusive,
  half-open ranges), ordering/stability guarantees, error-vs-skip rules,
  normalization/escaping details, and how multiple flags/options interact.
- Several of those behaviors are easy to overlook on a single reading (e.g.
  "nulls sort last regardless of direction", "trailing data after a closing
  quote raises", "negative zero is suppressed even under `percent=True`",
  "`..` is dropped at the root but kept literally in relative paths") — but
  every one of them is explicitly written down. Difficulty is breadth ×
  subtlety of *stated* requirements, not hidden expectations.
- **The fairness rule is absolute**: every grader test corresponds to a
  requirement explicitly numbered in the target file's docstring (or
  restated in the prompt). No grader test checks an undocumented
  "gotcha". A handful of grader tests are integration tests that combine
  two or more already-stated rules in one scenario (e.g. testing `..`
  cancelling two preceding segments at once, or `percent` + negative-zero
  together) — these still trace back to explicitly stated rules, not new
  ones.

## The no-verification-instruction regime

Unlike `benchmarks/agent-tasks/`, this suite has **no `tests_visible/`
directory anywhere** and the prompts **never instruct the agent to test,
verify, or check its work**, and never mention grading or hidden tests.
Each prompt only names the file to modify and states (or points to) the
complete requirement list. Whether the agent chooses to write its own
throwaway checks is left entirely to its own judgment/habits — this is
part of what the suite is measuring.

## Directory layout

Each task lives at `benchmarks/agent-tasks-hard/<task-id>/` and contains:

- `task.json` — `{"id", "title", "prompt", "timeout_seconds"}`. `prompt`
  is the complete instruction text given to the agent verbatim.
- `workspace/` — a single starter Python module (stdlib only, Python
  3.11+) with the target function's signature and an exhaustive docstring;
  the function body raises `NotImplementedError`. This is the only content
  the agent ever sees.
- `grader/test_grader.py` — one held-out pytest file, copied into the
  workspace root after the agent's run and executed with
  `python -m pytest -q` from that root (so it does a top-level
  `from <module> import <fn>`).
- `reference/` — a correct, verified reference implementation of the same
  file, proving the task is solvable. Maintainer-only; never shown to the
  agent and never copied by the harness at run time.

## Per-requirement grader naming convention

Every requirement numbered in a target docstring gets its own test
function named `test_req_<nn>_<slug>`, where `<nn>` matches (or closely
tracks) the docstring's numbered rule and `<slug>` is a short description.
When a rule's `#` doesn't have a 1:1 test (e.g. two closely related rules
are most naturally checked together, or one rule needs more than one
assertion to pin down), the tests use suffixes like `test_req_05_and_06_...`
or `test_req_08b_...` so the failure output still points a maintainer (or a
post-hoc failure analysis) straight at the missed requirement. A few
`test_<free_form_name>` functions per task are integration checks that
exercise a combination of already-numbered rules in one scenario; they
never introduce a new, undocumented requirement.

## Task menu

1. `csv-field-split` — quoted-field record splitter with doubled-quote
   escaping, custom separator, and empty/trailing-field rules.
2. `multi-key-sort` — stable multi-key record sorter with per-key
   direction, null-last placement, and type-mismatch errors.
3. `interval-merge-clamp` — half-open interval merge with touch/overlap
   rules and optional `lo`/`hi` clamping.
4. `ascii-table-render` — bordered text table renderer with per-column
   alignment, truncation-with-ellipsis, and `len()`-based widths.
5. `glob-matcher` — `*`/`?`/`[...]` glob matcher with ranges, negation,
   and backslash escaping, implemented without the `re` module.
6. `number-formatter` — numeric string formatter with round-half-to-even,
   thousands separators, percent mode, and negative-zero suppression.
7. `path-normalizer` — POSIX-style path normalizer with `.`/`..`
   resolution rules that differ for absolute vs. relative paths.
8. `event-window-aggregate` — tumbling-window event log aggregation with
   boundary, gap-filling, and duplicate-timestamp rules.

## Running a task through the harness (manually)

```
task=<task-id>
workdir=$(mktemp -d)
cp -R benchmarks/agent-tasks-hard/$task/workspace/. "$workdir"/
# ... run the agent in $workdir with the prompt from task.json ...
cp benchmarks/agent-tasks-hard/$task/grader/test_grader.py "$workdir"/
(cd "$workdir" && python -m pytest -q)
```

## Adding a new task

1. Pick a kebab-case id and a domain distinct from existing tasks.
2. Create `benchmarks/agent-tasks-hard/<id>/{task.json,workspace,grader,reference}`.
3. Write the starter module: signature + a docstring that numbers every
   graded behavior (10-15 of them), with a `NotImplementedError` body.
4. Write `grader/test_grader.py` with one `test_req_<nn>_<slug>` per
   numbered requirement.
5. Write `reference/` with a correct implementation, proving solvability.
6. Verify: grader must FAIL against the starter `workspace/`, and PASS
   against `workspace/` overlaid with `reference/`. Count the grader
   tests (must be 10-15) and confirm each maps to a requirement stated in
   the prompt/docstring.
7. Keep `task.json`'s `prompt` free of any mention of grading, hidden
   tests, or an instruction to verify/test the work.
