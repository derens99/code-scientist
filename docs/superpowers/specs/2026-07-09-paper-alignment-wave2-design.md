# Paper Alignment Wave 2 Design — Evaluation Methods + Review Parallelism

Date: 2026-07-09. Branch: `feature/paper-alignment-wave2`. Follows Wave 1 (merged to master at `0d5cd70`).

## Goal

Implement the two evaluation methods the audit (`docs/paper-alignment-audit-2026-07-04.md`) lists as unimplemented-as-methods, plus the review-parallelism optimization deferred from Wave 1:

1. **Elo-vs-correctness concordance** (paper §4.1, the GPQA study): objective-answer benchmark format, ground-truth grading of hypotheses, Elo bucketing with per-bucket accuracy, top-1 correctness, and a pairwise concordance index.
2. **Temporal Elo scaling trajectory** (paper §4.2, Fig 4): best-Elo and top-10-average-Elo recorded over the tournament match sequence, within a run.
3. **Real review parallelism**: per-task isolation of the two shared drain buffers (`EvidenceStore._retrieval_memory`, `_LLMTraceMixin._llm_interactions`) via thread-local storage, then narrowing the Wave 1 `state_lock` so concurrent review tasks actually overlap on the LLM/retrieval work.

Out of scope (later waves): LLM-as-judge preference auto-evaluation, frontier-model baseline arms, agent-driven retrieval loop, in-loop code execution.

## Design

### 1. Elo-vs-correctness concordance

**Paper mapping.** In §4.1 the co-scientist answers questions with known-correct answers; the study asks whether higher-Elo hypotheses are more often correct. Coding-domain translation: a run whose objective is an *objective question* (a coding question with a verifiable answer key); each hypothesis declares an answer in its text; grading extracts the declared answer and compares to ground truth.

**New module `src/code_scientist/concordance.py`** (evaluation.py is already large; concordance is one clear responsibility):

- `load_objective_benchmark(path)` — JSON fixture `{"name": str, "question": str, "answer": str, "answer_pattern": optional regex str}`. Default pattern: `answer\s*[:=]\s*([A-Za-z0-9_.-]+)` (case-insensitive), matched over `title + claim + rationale`.
- `grade_hypotheses(benchmark, hypotheses, grades=None)` → `dict[hypothesis_id, bool]`. Extract each hypothesis's declared answer via the pattern; compare case-insensitively to `benchmark["answer"]`. Hypotheses with no extractable answer are ungraded (excluded from the dict). An optional explicit `grades` map (`{hypothesis_id: bool}`, e.g. from an external grader or human) overrides/extends extraction.
- `compute_elo_concordance(benchmark_name, hypotheses, correctness)` → `EloConcordanceResult`:
  - Graded set = active hypotheses (status not in inactive set) present in `correctness`.
  - **Buckets**: sort graded by Elo desc, split into up to 4 near-equal contiguous buckets (fewer when <4 graded); per bucket record elo_max/elo_min/count/accuracy.
  - **Top-1**: whether the highest-Elo graded hypothesis is correct.
  - **Concordance index** (pairwise AUC): over all (correct, incorrect) pairs, fraction where the correct one has strictly higher Elo (ties 0.5); 0.5 when either class is empty.
  - Overall accuracy, graded/ungraded counts.

**New model `EloConcordanceResult`** (models.py, frozen dataclass): `id, benchmark_name, question, graded_count, ungraded_count, overall_accuracy, top_hypothesis_id, top_hypothesis_correct, concordance_index, buckets (list[dict]), notes (list[str])`. RunState gains `elo_concordance: list[EloConcordanceResult] = []` with tolerant `from_dict` default (old state.json keeps loading).

**CLI**: `code-scientist elo-concordance <state.json> --objective-benchmark <fixture.json> [--grades <grades.json>]` — loads state, grades, computes, appends the result to `state.elo_concordance`, saves state, prints a summary. Grades JSON: `{"<hypothesis_id>": true|false, ...}`.

**Reporting**: `render_report` gains an "Elo Concordance" section (per result: accuracy, top-1, concordance index, bucket table) rendered only when results exist. `audit_capability_study_coverage` gains an `elo_concordance_count` entry so the study coverage audit tracks the method (closing the audit's note that coverage is silent on it).

### 2. Temporal Elo trajectory

**New model `EloTrajectoryPoint`** (models.py, frozen): `cycle: int, match_index: int, match_id: str, best_elo: float, top_avg_elo: float, active_count: int`. `top_avg_elo` = mean Elo of the top min(10, n) active hypotheses (paper's top-10 average). RunState gains `elo_trajectory: list[EloTrajectoryPoint] = []`, tolerant default.

**Recording**: in `run_research_cycle`'s `execute_ranking` loop (supervisor.py), after each match is appended, compute the point from `_active_hypotheses(hypotheses)` and append to a run-scoped `elo_trajectory` list threaded into `current_state()`/persistence like `matches`. `match_index` is the global running index (`len(elo_trajectory)`), monotonically increasing across cycles.

**Reporting**: "Elo Trajectory" section — point count, first/last/max best-Elo, first/last top-avg — rendered when points exist. Coverage audit gains `elo_trajectory_point_count`.

The existing cross-run `ScalingCurvePoint` proxy stays untouched; the trajectory is the within-run Fig-4 method.

### 3. Per-task drain buffers + narrowed review lock

**Why thread-local instead of threading task ids through signatures**: every task executes wholly within one worker thread, and each producer (`retrieve()`, `complete()` tracing) is drained by a consumer inside the same task closure. `threading.local()` buffers therefore give exact per-task isolation with zero public-signature changes, and at `review_concurrency=1` everything runs on one thread so behavior is byte-identical. ThreadPoolExecutor thread reuse is safe because each task drains its own records before its closure returns.

- `EvidenceStore._retrieval_memory` → thread-local list (`self._retrieval_local = threading.local()`; accessor returns the current thread's list, creating it on first use). `consume_retrieval_memory` drains only the current thread's list.
- `_LLMTraceMixin._llm_interactions` → same pattern per agent instance.
- **Narrow the lock** (supervisor.py): `_review_for_plan` gains a `state_lock: threading.Lock | None = None` parameter; the retrieval + LLM review work runs unlocked, and only the shared-list mutations (`reviews`/`agent_traces` appends, retrieval-memory extend, `reviewed`/`hypotheses` bookkeeping in the closure) acquire the lock. The `prior_reviews` snapshot is still taken under the lock.
- **Tests replace the Wave 1 serialization test**: the old `max_observed == 1` assertion (which pinned full serialization) is replaced by (a) a parallelism test proving overlap now occurs (`max_observed >= 2` with `review_concurrency=3` and an instrumented sleep inside the unlocked region), (b) an attribution test proving two concurrent grounded review tasks each drain only their own retrieval records (no stolen/lost records, correct task_id enrichment), and (c) the existing output invariants (no duplicate/lost reviews). Deterministic default runs stay byte-identical at concurrency=1.

## Verification

- TDD per task; `uv run pytest -q` green throughout (baseline 348).
- Old-state loading guarded by round-trip tests for the two new RunState fields.
- Smoke run demonstrating a populated trajectory; an end-to-end concordance CLI test with a synthetic objective fixture.
- Web suite + typecheck unaffected (new fields are additive JSON).
- Audit doc annotated: the two evaluation-method gaps marked resolved.

## Non-goals / honesty constraints

- Concordance grades only what is objectively extractable or explicitly supplied; it never infers correctness from Elo or review scores (that would be circular).
- Deterministic-provider runs remain scaffolding: the concordance method is meaningful only over research-grade runs on real objective questions.
