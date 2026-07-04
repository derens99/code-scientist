# Paper Alignment Wave 1: Core-Loop Fidelity And Defect Fixes

Date: 2026-07-04
Status: approved
Source audit: `docs/paper-alignment-audit-2026-07-04.md`
Paper: "Towards an AI co-scientist" (arXiv 2502.18864), local text `tmp/pdfs/2502.18864.clean.txt`

## Goal

Make the existing control loop behave the way the paper describes it, fixing the seven verified defects and de-stubbing two named mechanisms. This wave changes behavior of existing machinery; it adds no new subsystems.

## Scope (8 items)

### 1. Hypothesis safety quarantine enforcement

Paper requirement (§6): unsafe hypotheses are excluded from the tournament, not developed further, and not presented as research output.

- Add hypothesis status value `quarantined`.
- Set it when `review_hypothesis_safety` rejects a hypothesis at creation/ingestion, or when a `safety_review` reflection produces a reject decision for it.
- Exclude `quarantined` (alongside `merged_duplicate`) from: pair scheduling in `_schedule_pairs`, evolution leader selection, generation-allocation statistics, and the ranked-hypotheses / research-overview sections of reports and the workbench.
- Quarantined hypotheses remain in `state.json` and appear in the report's safety section with the triggering decision/flags (audit trail instead of silent deletion).
- Backward compatibility: old state files with no `quarantined` status load unchanged; no schema migration.

### 2. Meta-review feedback wired into agent prompts

Paper requirement (§3, "learning without backprop"): meta-review feedback is appended to agent prompts in the next iteration.

- Add an `agent_feedback` parameter to the generation, reflection/review, ranking, and proximity prompt builders (Evolution already has one). The supervisor threads the latest agent-scoped meta-review feedback into each agent invocation.
- LLM paths: feedback appears as a clearly-delimited "Meta-review feedback from prior cycles" block in the prompt.
- Deterministic paths: behavior conditions on feedback rather than annotating output post-hoc — generation avoids proposal patterns whose weakness terms appear in feedback; reviews add explicit checks for previously-flagged weakness terms; ranking/proximity record the feedback context in traces without rewriting artifacts.
- Remove the post-hoc artifact mutation in `_apply_generation_feedback`, `_apply_review_feedback`, and the match/edge/overview equivalents. Trace notes recording "feedback was available" stay.
- Fix `FeedbackLoopEvaluation`: the adoption/quality proxy becomes weakness-recurrence measurement — the rate at which weakness terms flagged by meta-review in cycle N recur in reviews of cycle N+1 artifacts — instead of detecting supervisor-injected strings. Record before/after recurrence rates per feedback item.

### 3. Close the supervisor statistics loop

Paper requirement (§3): supervisor statistics inform resource allocation and terminal-state decisions.

- Effective scheduler weights: `score_task_priority` (via `_task_priority`) uses the most recent context snapshot's adjusted `scheduler_weights` when present, falling back to `plan.scheduler_weights`. `_adjust_scheduler_weights` output therefore steers next-cycle task priorities.
- Termination criteria: evaluate `plan.termination_criteria` at each cycle end. Supported deterministic criteria (parsed tolerantly from the existing free-text list):
  - `min_hypotheses: N` / "at least N hypotheses" — N active non-quarantined hypotheses exist.
  - `elo_plateau: N` / "elo plateau" — best Elo unchanged (< 1.0 delta) for N consecutive cycles (default 2).
  - `all_reviewed` — every active hypothesis has at least one review.
  Unrecognized criteria are recorded as `unevaluated` and never terminate a run.
- When criteria are met, bounded runs stop early and continuous runs stop; the final context snapshot records `termination_reason`.

### 4. Rank-tiered debate depth

Paper requirement (§3 tournament): top-ranked pairs get multi-turn scientific debates; lower-ranked pairs get single-turn comparisons.

- Per-pair decision at match execution time: if both hypotheses are in the top Elo tier (top 25% of active hypotheses by Elo, minimum tier size 2), use multi-round debate; otherwise single-turn debate comparison.
- The existing plan-level simulated-debate flag becomes an override: force-all-multi-round or force-all-single-turn. Default (no override) is the tiered rule.
- Match records note the tier decision (`debate_tier: top|standard`) in existing match metadata.

### 5. De-stub research expansion and tournament review

- `research_expansion_from_meta_review` (generation mode) receives existing hypothesis titles/claims and the latest `ResearchOverview`. Deterministic path: propose in directions absent from current claims/cluster topics (token-level absence check against existing claims). LLM path: prompt includes the overview summary and existing titles with an instruction to target unexplored areas. Output records which explored-area gaps it targeted.
- `recurrent_tournament_review` (reflection mode) receives the hypothesis's match record (wins/losses/ties, opponents) and recurring weakness terms from prior reviews. Deterministic path: findings cite the win/loss record and recurring weaknesses; score reflects tournament performance signal. LLM path: prompt includes the match summary. No longer a relabeled initial review.

### 6. Bounded concurrency for the review stage

- `run_research_cycle` passes `max_concurrency` (default 4, capped by hypothesis count) to `run_task_worker` for the per-hypothesis review stage only; all other stages remain sequential.
- Per-task state persistence moves to after-pool-completion for concurrent pools (single write), keeping `state.json` writes single-threaded. Task lifecycle transitions remain per-task.
- A supervisor/CLI knob (`review_concurrency`) can set 1 to restore fully sequential behavior.

### 7. Web-search endpoint/parser fix

- Change the `WebSearchTool` default `base_url` to the DuckDuckGo HTML endpoint that the existing HTML fallback parser targets (`https://html.duckduckgo.com/html/`), with the query-parameter format the parser's fixtures use.
- The Bing RSS path stays functional when a caller configures a `base_url`/format that returns RSS.
- Add a fixture test proving the default configuration parses a realistic DuckDuckGo HTML page into results (the current default provably cannot).

### 8. Safety-critic failure auditing

- When the LLM safety critic raises (`LLMResponseError` or transport error), the resulting deterministic-fallback decision carries an explicit `safety-critic-error` flag, and an `EvidenceSafetyFinding`-style audit record is persisted (for goal decisions, the flag lives on the goal `SafetyDecision`).
- New safety-policy option `fail_closed: true` (default false): on critic failure, goals are blocked pending manual review (`manual-review-required` flag) instead of falling back to deterministic-allow.

## Non-Goals (later waves)

Objective benchmark / Elo-concordance evaluation (Wave 2), temporal Elo history (Wave 2), agent-driven retrieval and execution tools (Wave 3), adversarial dataset harness and activity log (Wave 4), weight-sampled cross-stage task dispatch (deferred; this wave only closes the weight feedback loop within the existing stage structure).

## Acceptance Criteria

1. A hypothesis whose safety review rejects it never appears in matches, evolution lineage, or ranked report output for that or later cycles; it appears in the report safety section. Covered by supervisor + reporting tests.
2. With a fake provider client, the prompts passed to generation/review/ranking/proximity contain the prior cycle's meta-review feedback text; no supervisor code path mutates already-created hypothesis rationale or review findings with feedback strings. Feedback-loop evaluation records report weakness-recurrence rates, and a test shows the metric is not satisfied by mere string injection.
3. A run whose cycle-1 snapshot adjusts scheduler weights produces different task priority ordering in cycle 2 than an identical run without the adjustment (test via `score_task_priority` with snapshot present/absent). A plan with `min_hypotheses: 2` terminates a 5-cycle run early with `termination_reason` recorded.
4. In a tournament with ≥ 8 active hypotheses, matches between two top-quartile hypotheses use multi-round debate and other matches use single-turn, verified by match metadata; plan override forces either mode globally.
5. Research-expansion output differs when existing hypotheses cover a topic vs. not (deterministic test); recurrent tournament review findings reference actual match counts.
6. A cycle with 4+ review tasks and `review_concurrency=2` completes all reviews with correct state and no duplicated task records; suite remains deterministic.
7. `WebSearchTool()` with default configuration parses results from a DuckDuckGo-HTML fixture.
8. A failing critic produces a decision carrying `safety-critic-error`; with `fail_closed`, the goal is blocked with `manual-review-required`.
9. Old `state.json` fixtures still load; `uv run pytest -q` and web `npm test`/typecheck pass.

## Risks

- Item 2 removes existing behavior (post-hoc annotation) that current tests may assert on; those tests change with the behavior, preserving their intent (feedback reaches agents) rather than their mechanism.
- Item 4 changes default match behavior; deterministic tests that assume single-turn matches for top pairs will be updated to set the plan override.
- Item 6 introduces threading; mitigated by restricting concurrency to the review pool and single-writer state persistence.
