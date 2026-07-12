# Agent Benchmark Task Suite

This directory holds a fixed suite of self-contained coding tasks used to
measure a headless coding agent's performance (e.g. `claude -p` runs) in
A/B experiments. Each task gives the agent a small Python workspace and a
natural-language prompt; after the agent finishes, a held-out grader test
suite is copied in and run. A task **passes** iff `python -m pytest -q`
exits 0 in the workspace after the grader files are copied in.

## Directory layout

Each task lives at `benchmarks/agent-tasks/<task-id>/` and contains:

- `task.json` — `{"id", "title", "prompt", "timeout_seconds"}`. `prompt`
  is the complete instruction text given to the agent verbatim. It never
  mentions grading, grader tests, or hidden tests.
- `workspace/` — the starter files shown to the agent: the module(s) to
  edit, and optionally `tests_visible/test_basic.py` with happy-path
  tests the agent can run itself. This is the only content the agent
  ever sees.
- `grader/` — one or more `test_grader*.py` files, held out from the
  agent. The harness copies these into the workspace root after the
  agent's run and executes `python -m pytest -q` from that root, so each
  grader file must import the task module as a top-level import (e.g.
  `from cache import SimpleCache` when the workspace contains
  `cache.py`).
- `reference/` — a correct reference implementation of the file(s) the
  agent is asked to modify, proving the task is solvable. This directory
  is for maintainers only: it is never shown to the agent and never
  copied by the harness at run time.

## The grader-held-out contract

- Graders are never present in the workspace the agent sees, and the
  prompt never hints at their existence or content.
- Graders must be a **strict superset** of the visible behavior: a lazy
  solution that only satisfies `tests_visible` (when present) should fail
  at least one grader test on a legitimate edge case.
- Graders must be deterministic — no network access, no wall-clock timing
  assertions, no unseeded randomness.

## The fairness rule

Every behavior a grader test checks must be clearly implied by the task
prompt and/or the docstrings already present in the starter workspace.
Graders must never test undocumented "gotchas" the agent had no way to
anticipate. The suite measures carefulness (reading the full spec and
handling edge cases it already implies), not mind-reading.

## Task kinds in this suite

- **Bug-fix** (`interval-merge-bugfix`, `csv-dedupe-bugfix`,
  `topo-sort-bugfix`): a module has one subtle bug; visible tests mostly
  pass on the happy path already, and the grader exercises the specific
  edge case the bug breaks.
- **Implement-from-spec** (`token-bucket-rate-limiter`,
  `text-wrap-justify`, `semver-compare`, `config-deep-merge`): function
  bodies raise `NotImplementedError`; a precise docstring specifies exact
  behavior, including edge cases (empty input, ties, negative numbers,
  malformed input).
- **Behavior-preserving change** (`flatten-iterative`,
  `lru-cache-bound`): the prompt asks for a structural or capability
  change (recursion removal, adding an eviction bound) while explicitly
  preserving existing observable behavior; the grader checks both the
  new requirement and the preserved behavior.
- **Edge-case hardening** (`log-parser-hardening`): a function already
  works on common input; the prompt lists additional required behaviors
  (skip blank/malformed lines, normalize case, filter unknown values) and
  the grader tests exactly those.

## Running a task through the harness (manually)

```
task=<task-id>
workdir=$(mktemp -d)
cp -R benchmarks/agent-tasks/$task/workspace/. "$workdir"/
# ... run the agent in $workdir with the prompt from task.json ...
cp benchmarks/agent-tasks/$task/grader/test_grader*.py "$workdir"/
(cd "$workdir" && python -m pytest -q)
```

## Adding a new task

1. Pick a kebab-case id and a domain distinct from existing tasks.
2. Create `benchmarks/agent-tasks/<id>/{task.json,workspace,grader,reference}`.
3. Write `workspace/` starter code (and optionally
   `workspace/tests_visible/test_basic.py`, happy-path only).
4. Write `grader/test_grader_<id>.py` — a strict superset of the visible
   behavior, testing only things implied by the prompt/docstrings.
5. Write `reference/` with a correct fix/implementation of the same
   file(s), proving solvability.
6. Verify: grader tests must FAIL against the starter `workspace/` and
   PASS against `workspace/` overlaid with `reference/`; any
   `tests_visible` must PASS against the reference overlay too.
7. Keep `task.json`'s `prompt` free of any mention of grading or hidden
   tests.
