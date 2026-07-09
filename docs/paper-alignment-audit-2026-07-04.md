# Paper Alignment Audit — 2026-07-04

Fresh audit of Code Scientist against "Towards an AI co-scientist" (arXiv 2502.18864, local text at `tmp/pdfs/2502.18864.clean.txt`), verified against the working tree at commit `64c8e55`. This supersedes the coverage assessment in `docs/paper-implementation-gap-analysis.md` (2026-06-25), which is stale in both directions: it understates some delivered work (task queue, scientist-in-the-loop, evidence safety) and overstates other coverage (hypothesis safety enforcement, meta-review feedback wiring, Elo/scaling evaluation methods).

Verification at audit time: `uv run pytest -q` 303 passed; web `npm test` 31 passed; web typecheck clean.

## Verified Defects (behavior contradicts the code's own intent)

1. **Safety-rejected hypotheses are not excluded from the tournament.** The paper requires unsafe hypotheses be excluded from ranking, not developed further, and not shown to the user (paper §6). Safety reviews run and score, but tournament pairing filters only `merged_duplicate` (`supervisor.py`, `_schedule_pairs`), so flagged hypotheses still enter Elo matches, can be selected as evolution leaders, and headline reports. **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
2. **Web-search default endpoint/parser mismatch.** `WebSearchTool` defaults to a Bing URL with `format=rss`, but the HTML fallback parser targets DuckDuckGo markup (`tools.py`). The default configuration likely parses zero results. **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
3. **LLM safety critic fails open silently.** On `LLMResponseError` the critic falls back to deterministic-allow with no recorded finding that the critic failed (`safety.py`). **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
4. **Scheduler weight adjustment is write-only.** `_adjust_scheduler_weights` computes updated weights each cycle and persists them in context snapshots, but `_task_priority` reads only the immutable `plan.scheduler_weights`. Same for `next_actions`. The paper's statistics→allocation loop is open. **Resolved in Wave 1 (`feature/paper-alignment-wave1`)** for the scheduler-weight-consumption half (task priorities now read snapshot-adjusted weights); `next_actions` consumption is not addressed.
5. **Meta-review feedback never reaches agent prompts.** Feedback is applied to already-produced artifacts (rationale strings, review findings) after the fact; only the Evolution prompt receives feedback. The paper's central "learning without backprop" mechanism (feedback appended to prompts in the next iteration) is simulated by post-hoc annotation, and the `FeedbackLoopEvaluation` adoption metric circularly detects the injected strings. **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
6. **Worker concurrency is dead code.** `run_task_worker(max_concurrency=…)` exists but `run_research_cycle` always calls it with the default of 1. **Resolved in Wave 1 (`feature/paper-alignment-wave1`)** for review-stage tasks (bounded concurrency for per-hypothesis review); other stages still run at concurrency 1. **Wave 2 (`feature/paper-alignment-wave2`)** narrowed the review `state_lock` to only the shared-list mutations (reviews/reviewed/hypothesis bookkeeping) and made the retrieval-memory and LLM-trace drain buffers thread-local, so bounded review concurrency now genuinely overlaps LLM calls and retrieval work rather than serializing them behind a wide lock.
7. **`termination_criteria` is parsed and persisted but never evaluated** — runs terminate on fixed cycle counts/wall time only. **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**

## Named Paper Mechanisms That Are Stubs

- `research_expansion_from_meta_review` re-tags plain `generate()`; it never sees the research overview or existing hypotheses (paper: target unexplored areas). **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
- `recurrent_tournament_review` is a relabeled initial review; it consults no tournament state (paper: analyze recurring issues from tournament results). **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
- Rank-tiered debate depth is missing: the paper gives top-ranked pairs multi-turn debates and lower-ranked pairs single-turn; here `_use_multi_round_debate` is a plan-global flag that defaults off. **Resolved in Wave 1 (`feature/paper-alignment-wave1`).**
- Deep verification runs three canned queries instead of decomposing into assumptions/sub-assumptions and judging whether a flawed assumption is fundamental.
- Simulation/observation reviews are evidence-presence checks, not step-wise simulation or per-observation explanatory judgments.
- Proximity "clusters" are per-edge labels, not a graph partition; cluster statistics are approximate.
- The task queue orders work only *within* a fixed pipeline stage; weights never choose whether the next unit of compute is generation vs review vs ranking.

## Evaluation-Method Gaps (unimplemented as methods, not merely un-run)

- **Elo-vs-correctness concordance (paper §4.1, the GPQA study):** no objective-answer benchmark, no ground-truth grading, no Elo bucketing with per-bucket accuracy, no top-1 accuracy. The existing `elo_benchmark_correlation` correlates Elo against fixture/keyword scores, and benchmark "pass" is lexical term-matching over hypothesis text. **Resolved in Wave 2 (`feature/paper-alignment-wave2`)**: `concordance.py` loads an objective-answer benchmark, grades hypotheses (declared-answer extraction with explicit-grade override), and `compute_elo_concordance` produces Elo buckets, per-bucket accuracy, top-1 verdict, and a concordance index; the `elo-concordance` CLI subcommand persists results to `state.elo_concordance` and the report.
- **Temporal Elo scaling trajectory (paper §4.2, Fig 4):** no Elo history is recorded over the match sequence; the current "scaling curve" is a cross-run proxy-delta keyed to budget labels, not best-Elo / top-10-avg-Elo over tournament time. **Resolved in Wave 2 (`feature/paper-alignment-wave2`)**: every tournament match now appends an `EloTrajectoryPoint` (cycle, global monotonic match index, best Elo, top-10-avg Elo, active count) to `state.elo_trajectory`, rendered in the "Elo Trajectory" report section.
- **LLM-as-judge preference auto-evaluation (paper §4.3, Fig 8):** blind packets and ingestion exist, but nothing automatically produces judge choices.
- **Frontier-model baseline arms (paper §4.2, Fig 5):** only one deterministic single-shot baseline arm exists.
- The `study` coverage audit does not track Elo-concordance or temporal-Elo at all — consistent with those being unimplemented concepts. **Resolved in Wave 2 (`feature/paper-alignment-wave2`)**: `audit_capability_study_coverage` now reports `elo_concordance_count` and `elo_trajectory_point_count`.

## Grounding Gaps

- **No agent-driven retrieval loop:** all web/literature queries are human CLI parameters collected once before the run; no agent generates or iterates queries per hypothesis (the paper's core generation/reflection grounding loop).
- **No in-loop code-execution tool:** the coding-domain analog of AlphaFold-as-a-tool (run tests, linters, type-checkers to empirically check a hypothesis during review) is absent; a command-runner exists only in the separate prospective-validation path.
- **Tool budget is a label:** `tool_budget` is plumbed through manifests and scaling records but nothing enforces or allocates it.
- Repository search is line-grep, not semantic; source scoping from follow-up directions is a keyword priority nudge, not a retrieval restriction.

## Safety Gaps Beyond the Quarantine Defect

- Red-team suite is 11 hardcoded cases phrased in the exact vocabulary of the keyword gates (self-confirming), vs the paper's 1,200 adversarial goals across 40 topics. No loadable adversarial dataset, no paraphrase/obfuscation variants, no coding-domain topic taxonomy.
- No append-only activity log of tool invocations, external fetches, quarantine decisions, and critic calls (paper: request logging, comprehensive logging); only end-of-task state snapshots.
- No cross-cycle unsafe-direction trend alerting from meta-review; no manual-review queue for escalated items (escalation hard-blocks).

## What Is Genuinely Done

Control-loop shape and state model; persisted priority task queue with lifecycle/resume; context memory with snapshots, traces, transcripts, retrieval memory; all six agents present with deterministic + provider paths; Elo tournament with debate transcripts and pair scheduling per the paper's two prioritization rules; proximity dedup/merge/diversity controls consumed by scheduling and evolution; evolution strategies with parent-preserving lineage; goal/evidence safety screening with configurable policies; extensive scientist-in-the-loop workbench (manual hypotheses/reviews genuinely re-enter the tournament); blind human-study packet/ingestion infrastructure; the Claude Code/Codex agent-packet bridge.

## Not Codeable Here (external dependencies)

Real human preference/rubric studies (§4.3, §4.5.1), human "best guess" arms, trusted-tester program, external embedding/search services, domain database connectors (GitHub/PyPI/CVE-style adapters need network integrations and are separate decisions).

## Consolidated Top Codeable Gaps (ranked by paper-faithfulness value)

1. Wire meta-review feedback into agent prompts (generation, reflection, ranking, proximity) and deterministic heuristics; fix the circular adoption metric. (Core, paper's central self-improvement loop.)
2. Enforce hypothesis safety quarantine across pairing, evolution, and reports. (Safety defect.)
3. Elo-vs-correctness concordance on an objective coding benchmark: ground-truth checker, Elo buckets, per-bucket accuracy, top-1. (Evaluation §4.1.)
4. Close the supervisor statistics loop: consume adjusted scheduler weights next cycle; evaluate plan `termination_criteria`. (Core §3.)
5. Temporal Elo trajectory: record per-match Elo history; compute best/top-k Elo over tournament-time buckets across goals. (Evaluation §4.2.)
6. Agent-driven query generation + per-hypothesis iterative retrieval using the existing tools. (Grounding.)
7. In-loop sandboxed test/lint/typecheck runner as an agent tool. (Grounding, strongest empirical signal in this domain.)
8. Rank-tiered debate depth per pair. (Core §3 tournament.)
9. Adversarial safety dataset harness: loadable JSONL suite, coding-domain taxonomy, paraphrase/obfuscation variants, per-topic pass rates. (Safety §4.4.)
10. Real weighted/concurrent task dispatch: weight-sampled task-kind selection under dependency constraints; enable bounded concurrency for independent tasks. (Core §3.)
11. `research_expansion_from_meta_review` and `recurrent_tournament_review` consume the state they are named after. (Core agents.)
12. Append-only JSONL activity log for tool calls, fetches, safety decisions, critic failures. (Safety/logging.)
13. Fix the web-search endpoint/parser mismatch; audit critic fail-open with a recorded finding and optional fail-closed mode. (Defects.)
14. Enforce the tool budget in the task worker. (Grounding/scheduling.)
15. LLM-as-judge blind preference auto-evaluation reusing existing packets/ingestion (needs provider key at runtime, wiring is codeable).
