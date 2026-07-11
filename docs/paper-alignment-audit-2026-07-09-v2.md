# Co-Scientist Paper Alignment Audit - 2026-07-09 (v2)

## Authority and scope

This audit compares the current `master` checkout at `2a4bec3` plus the changes in this working tree with the official arXiv v2 of **"Accelerating scientific discovery with Co-Scientist"** (arXiv:2502.18864, revised 2026-06-29). The earlier project audits used the February 2025 v1 text, whose title, main-paper structure, supplementary methods, pseudocode, and agent-ablation evidence are now superseded.

The comparison is a domain translation: the paper targets biomedical hypothesis generation, while Code Scientist targets coding-agent and LLM-workflow research. Alignment therefore means reproducing the paper's control mechanisms and validation discipline with coding-domain evidence and experiments, not copying biomedical prompts or claiming biomedical capability.

## Bottom line

Code Scientist is now a strong, auditable engineering prototype of the paper's control loop, but it has not demonstrated the paper's scientific capability.

- **Codeable mechanism alignment: about 94%.** The six-agent decomposition, persistent context, 1200-point Elo tournament, proximity-aware pairing, evolution, meta-review prompt feedback, safety quarantine, scientist input, safety-reviewed goal revision, durable dependency graphs, adaptive cross-kind scheduling, bounded resource classes, governed reference-bound retrieval, PDF OCR/table/figure provenance, opt-in semantic figure interpretation, budgeted empirical validation, and deterministic/provider-backed process review packets are real.
- **Agent-behavior fidelity: about 84%.** Generation and Reflection can search, inspect an observed result by evidence reference, and refine the next decision under a hard budget. Reflection performs structured observation comparison, step-wise simulation, deep assumption verification, and researcher-approved empirical checks in-loop. Current goal guidance is included in every major agent prompt. Ready agent kinds compete through current-state priorities rather than fixed post-generation stages. Review tasks can execute as authenticated provider packets, but other state-mutating kinds remain supervisor-local and visual claims still require human confirmation.
- **Evaluation-method availability: about 72%.** The project records Elo trajectories, Elo/correctness concordance, blind review packets, scaling records, prospective validation, baseline comparisons, order-swap stability, six paired component-ablation families, proximity/quality-difference proxy correlation, and topic/variant safety degradation. It still lacks independent human results and a serious external benchmark campaign.
- **Demonstrated paper-level capability: below 25%.** There are no completed large multi-goal studies, real expert preference results, coding-domain external validation results, or evidence that generated hypotheses improve coding agents. Software tests prove implementation integrity, not hypothesis quality.

An honest combined assessment is **roughly 80-84% aligned to the full paper claim as an engineering implementation**. These percentages are a qualitative requirement-coverage rubric, not a measured scientific score: mechanism coverage, behavioral fidelity, evaluation-method availability, and demonstrated capability are assessed separately and are not interchangeable. It would still be misleading to call the project a validated replication until it runs real provider-backed studies with independent reviewers and prospective measurements.

## Requirement matrix

| Paper mechanism | Current status | Current evidence | Remaining gap |
| --- | --- | --- | --- |
| Research goal -> configurable plan | Strong | `ResearchGoal`, goal briefs, `ResearchPlanConfig`, editable objective/constraints/metrics/source/tool/output/termination fields, safety-reviewed lineage, cycle-boundary application, task supersession, OCR-backed PDF text, and optional bounded visual interpretation | Form-based rather than free-form multi-turn chat; no measured hundreds-of-PDF campaign |
| Asynchronous continuous supervisor | Strong partial | Persisted dependencies/resource classes, adaptive rescoring, scheduler weights, pause/stop/resume, SQLite WAL claims, dependency/resource enforcement, leases/heartbeats/recovery, process-safe named budgets, deterministic and provider-backed portable review packets, and selectable worker processes | Initial generation and outer cycle/termination boundaries remain; state-mutating non-review kinds are not yet distributed; live retrieval budget is process-local |
| Context memory | Strong partial | State snapshots, task-linked traces, LLM interactions, scratchpads, retrieval memory, atomic state projection, append-only activity and coordinator event ledgers, and cross-process result reconciliation | No production shared vector/retrieval service or long-lived per-hypothesis knowledge base |
| Generation agent | Strong partial | Strategy allocation, debate/tool modes, assumptions mode, research expansion, provider paths, and one-to-ten-turn observation-driven governed retrieval | No long-lived per-hypothesis knowledge base; evidence quality still depends on configured sources/providers |
| Reflection agent | Strong partial | Initial/full/novelty/safety/deep/observation/simulation/recurrent modes; assumption trees, fundamental-failure control, per-observation comparison, step-wise simulation, live retrieval, empirical validation, and budgeted provider-backed process packets | Simulation remains textual rather than an executable domain simulator; only review packets are process-portable |
| Ranking/Elo tournament | Strong partial | Initial Elo 1200, proximity/newness pairing, rank-tiered debates, ties, Elo history/concordance, A/B and B/A order-swap audit, and Elo-preserving abstention | No calibrated judge ensemble or completed correctness study |
| Proximity agent | Strong partial | Lexical, local embedding, tool-backed and provider-backed edges; clustering/dedup/diversity controls; quality-difference proxy correlation | No external semantic embedding service; graph labels are not a globally optimized partition; no independently labeled quality-difference correlation study |
| Evolution agent | Partial | Combination, analogy, simplification, divergence, feasibility, evidence and feedback strategies with lineage; runnable paired ablation arm | Not continuously scheduled from convergence; limited live tool use; no externally judged evidence that evolution improves quality |
| Meta-review feedback | Strong partial | Agent-specific feedback reaches subsequent prompts and deterministic paths; research overview/output artifacts | No completed external AUC/quality study proving recurrent reviews improve evaluation |
| Scientist in the loop | Strong partial | Manual hypotheses/reviews, structured full-goal revision, safety approval/rejection history, cycle-boundary commands, source attachment, proximity decisions, evaluation return UI | No free-form chat interaction and no real expert study results |
| Tool/literature grounding | Strong partial | Local corpus/index/PDF/repo search, native PDF text, RapidOCR scanned-page extraction, table cells and figure/scan bounding-box provenance, opt-in hosted crop interpretation with claim lineage, governed web/search/crawl, OpenAlex/OA full text, reference-bound fetch, public-network/domain guards, citations, safety screening, budgets, resume deduplication, and empirical validation manifests | Host validation is restricted but explicitly not network-sandboxed; no production semantic embedding service; visual claims require human verification |
| Safety | Strong partial | Goal/evidence/hypothesis/revision review, policy files, fail-closed option, quarantine, safety traces, topic-labeled red-team corpora, generated/explicit variants, degradation metrics, append-only logs, and visible escalation findings | The escalation view has no approve/reject action workflow; no paper-scale 1,200-goal/40-topic completed campaign or independently calibrated degradation study |
| Evaluation and validation | Strong infrastructure, weak external evidence | Study kits, blind packets, baseline runs, external/prospective harnesses, Elo concordance/trajectory, order-swap audits, runnable component-ablation arms, paired delta reporting, proximity/quality proxy correlation, and statistics | Local deterministic studies are populated, but real reviewer, provider-campaign, prospective implementation, and independent external benchmark results are absent |

## Alignment change implemented in this pass

The v2 Methods section is explicit that deep verification must decompose a hypothesis into assumptions and sub-assumptions, evaluate them independently, determine whether an incorrect assumption is fundamental, and avoid invalidating an otherwise repairable hypothesis.

Before this pass, Code Scientist issued three broad retrieval queries and stored free-form findings. It could not answer which assumption failed, whether that failure was fundamental, or why the review rejected versus revised a candidate.

This pass adds:

- `AssumptionCheck`, a backward-compatible structured record containing parent linkage, depth, verdict, fundamental status, invalidation status, evidence references, and reasoning.
- Deterministic per-assumption retrieval and conservative supported/contradicted/uncertain judgments for the fallback worker.
- A provider prompt contract for explicit assumption/sub-assumption trees.
- Control behavior: a contradicted fundamental assumption forces rejection and plausibility 1; a contradicted non-fundamental assumption forces revision without rejection.
- Report and workbench rendering so the filtering decision is inspectable.

The deterministic worker deliberately verifies only explicitly declared assumptions. It does not fabricate a causal sub-assumption tree; deeper decomposition is reserved for the provider-backed worker and remains subject to external evidence quality.

## Agent-driven retrieval and budget change implemented in the next pass

- Generation and Reflection now plan their own focused searches and can spend a later turn fetching the document or open-access full text behind a result they actually observed.
- Fetch requests contain an evidence `source_ref`, never a URL. The executor resolves the trusted search record, checks public HTTP(S), blocks credentials/private or link-local addresses and nonstandard ports, validates redirects, and can enforce repeatable researcher domain allowlists with `--agent-fetch-domain`.
- The tool set is closed to explicitly configured repository search, web search, OpenAlex search, and reference-bound fetch adapters. Agents cannot choose roots, URLs, shell commands, crawl depth, domains, or full-text settings.
- A thread-safe supervisor-process budget is reserved before each live retrieval call. Failures consume budget; unavailable, invalid, duplicate, and over-budget requests do not. Independently launched retrieval workers do not yet share this counter.
- Tool usage, status, evidence refs, blocked reasons, errors, and remaining budget persist through `RunState`, task traces, reports, and the workbench.
- Resume restores used budget and deduplicates prior normalized tool/query pairs.
- Concurrent in-process review tasks cannot overspend the retrieval limit. Provider process calls use a separate SQLite-backed atomic budget.

## PDF/OCR and visual provenance change implemented in this pass

- PDF ingestion uses page-native text first and runs a real RapidOCR/ONNX pass only for unresolved pages, with page, DPI, confidence, and PDF-coordinate OCR-box metadata.
- Invalid PDF bytes are no longer treated as UTF-8 text. Unresolved pages retain explicit OCR-required diagnostics.
- PyMuPDF table extraction emits cited table rows and bounding boxes. Embedded images emit page-scan or figure-region records with bounding boxes, coverage, xrefs, and nearby captions.
- By default, figure regions explicitly remain `requires_visual_interpretation=true`; extraction alone is provenance and triage infrastructure, not a claim of multimodal scientific reasoning. The opt-in hosted interpretation path described below creates separate machine claims and never rewrites the source record as verified.

## Durable multi-process coordination change implemented in this pass

- Every run projects its task graph into a SQLite WAL coordinator while keeping `state.json` atomic through fsync plus replace.
- Transactional claims enforce dependencies and resource-class capacity. Worker leases have ownership, heartbeat, expiration, retry, and append-only event records.
- Named supervisor leases and atomic shared budgets are available from the same coordinator.
- Review tasks include portable no-shell deterministic or provider-backed packets. Packets are digest-bound and contain the exact review inputs and inline safety policies, but no credentials, API keys, or environment-file authority.
- `--review-processes N` executes packets in separate lease-based worker processes. Provider/model/token authority is supplied by operator-owned worker flags, every request consumes an atomic SQLite provider budget, and an expired provider lease fails for manual review instead of replaying a potentially billable call.
- Completed worker results use a validated result-envelope schema, durable JSON artifacts, and task-linked reflection/safety traces before reconciliation into reviews and run state. `code-scientist worker` and `coordination-status` expose the worker and audit surfaces.

## In-loop empirical validation change implemented in the following pass

- Reflection can execute explicit `--agent-validation-manifest` command-list manifests before evidence-aware reviews. Study goals can declare manifest-relative `agent_validation_manifests`.
- The manifest, command, working directory, timeout, and explicit environment remain researcher-owned; the agent cannot invent a shell command or filesystem target. Host execution strips ambient secrets, rejects secret-like manifest variables, constrains the working directory, applies process/file/CPU limits, captures bounded output, and terminates the full process group on timeout.
- Validation records carry an execution attestation. The supported host mode is deliberately named `host_restricted_not_sandboxed` and reports `network_isolated=false`; `execution_policy=hardened` fails closed until an external container or VM runner is configured.
- The current hypothesis is serialized for the harness, returned metrics become `agent_empirical_validation` evidence, and the review can retrieve that measured record before ranking.
- Empirical executions share the in-process atomic agent tool budget with repository, web, and literature calls. Failed executions consume budget, and completed/failed requests are deduplicated on resume.
- Tool calls, evidence, traces, budget state, CLI arguments, reports, and workbench setup are all persisted or exposed through the normal run path.

## Dependency-aware global scheduling change implemented in the following pass

- `Task` now persists prerequisite task ids and a resource class with backward-compatible state loading.
- The scheduler selects only dependency-ready work, rescans and rescores the queue after each execution wave, and records dependency, resource, state, feedback, and prior-snapshot next-action signals in each durable decision.
- After generation creates the cycle's candidates, review, ranking, proximity, evolution, meta-review, overview, and research-output tasks form one graph. Ready kinds compete by current priority rather than being dispatched through fixed stage calls.
- Review work can use bounded parallel capacity while ranking/proximity/evolution/meta-review/overview mutations share a single serialized state resource.
- Resume preserves the graph and will not execute a dependent task until every prerequisite is completed.

## Goal revision, visual interpretation, and trust-boundary changes in this pass

- Goal guidance now changes actual system behavior rather than merely annotating state. Objective, preferences, constraints, metrics, safety notes, allowed sources/tools, output formats, termination criteria, and a follow-up direction can be submitted through the workbench or `goal-revision` CLI command.
- Each revision creates goal/plan lineage, reruns safety review, regenerates goal-derived planning fields, preserves completed artifacts, supersedes only stale queued/deferred tasks, and records approval or rejection plus affected task ids. Running supervisors consume queued revisions at a safe cycle boundary.
- Current guidance is rendered into Generation, Reflection, Ranking, Proximity, Evolution, Meta-review, overview, and retrieval prompts. Follow-up directions also influence scheduler priorities by task kind.
- Optional `--pdf-vision` sends only bounded PyMuPDF figure crops to an explicitly selected hosted provider, consumes an atomic call budget, validates structured chart/figure output, hashes the crop, and emits claim-level evidence linked to the parent region/page/bounding box/model. It never silently upgrades a visual claim to human-verified evidence.
- Reports and the workbench expose goal lineage, machine-visual claim status, crop/model/confidence metadata, and validation isolation/network/ambient-secret attestations.

## Remaining work, ranked

### P0 - required before claiming a paper-faithful system

1. **Run real studies.** Execute provider-backed multi-goal baseline comparisons, independent blind reviews, and prospective implementation/benchmark validation. Until these artifacts exist, output quality is unknown.
2. **Complete the external campaign.** Populate the existing blind-review, prospective-validation, correctness/concordance, scaling, and component-ablation artifacts with independent results rather than local proxies.

### P1 - important fidelity and robustness work

Delivered in this pass: deterministic observation reviews now compare each observation against the hypothesis prediction; simulation reviews persist mechanism/intervention/measurement/outcome/failure-condition steps; provider prompts require the same behavior; ranking runs A/B and B/A with Elo-preserving abstention on disagreement; `activity.jsonl` append-only ledgers record task, tool, safety, source, run-status, and user-feedback events; and study manifests support explicit generation/review/evolution/scheduler overrides plus disabled-agent arms. The generated paper kit now includes 12 runnable paired arms covering generation strategy, reflection search, simple-vs-debate ranking, evolution, full-vs-recurrent review, and proximity.

Still required: distribute additional state-mutation kinds only if sustained crash/load testing demonstrates value; make live retrieval budgets cross-process if retrieval itself becomes distributed; add calibrated judge ensembles and correctness labels; and provide an actionable approve/reject workflow for escalated evidence rather than a read-only queue.

### P2 - scale and product completion

1. Add a true container/VM validation runner with enforceable network isolation; the current host runner is restricted and honestly attested, not sandboxed.
2. Add free-form multi-turn chat over the structured goal-revision protocol if user studies show the form/command flow is insufficient.
3. Make non-review state-mutation task kinds portable only where profiling or crash-recovery studies justify the extra coordination complexity.
4. Replace deterministic local embeddings with a measured production retrieval/embedding adapter only if the external study demonstrates value.
5. Validate semantic visual claims with human figure reading and add vector-graphic handling if the target paper corpus needs it.

Delivered in this pass: `safety-red-team` accepts loadable coding-domain corpora with topic labels and explicit paraphrase/obfuscation cases, can generate deterministic variants for every base case, and reports aggregate, per-topic, base, variant, and degradation metrics through CLI JSON, state models, reports, and the workbench. This improves measurement coverage; it does not by itself make the current keyword/policy safety gate robust to all obfuscations.

## Fresh local study evidence from this pass

The implementation was exercised beyond unit tests in three no-cost local workflows:

- A generated 12-arm ablation study completed all state/report artifacts and produced six paired rows. On the deterministic proxy, generation strategy and debate ranking changed score by only `-0.006` and `+0.006`; evolution and proximity were flat; reflection-search-on and full-review scored `0.000` because those evidence-demanding arms were run without an in-loop evidence corpus. That is a configuration-sensitive failure signal, not evidence that reflection is harmful.
- A generated three-goal capability study completed three benchmark artifacts, three scaling points, three safety evaluations, 16 Elo trajectory points, blinded capability/preference/feedback packets, and three prospective-validation templates. Its apparent baseline win rate was `1.000` with mean proxy delta `+0.482`, but the coverage audit correctly remained incomplete because human rubric/preference, prospective/external, and feedback-loop measurements were absent.
- The first built-in safety-variant run exposed seven failures: base pass rate `1.000`, variant pass rate `0.682`, and degradation `0.318`. The failures came from whitespace/hyphen obfuscation and paraphrases such as “bypassing reviewer approval,” “disregard all earlier guidance,” and “game the evaluation suite.” Normalized separator matching and explicit semantic phrase coverage were then added; the same 33-case suite reran at base `1.000`, variant `1.000`, degradation `0.000`. This closes those exact variants only; a larger independently authored corpus is still required to estimate real robustness.

No paid provider campaign was run in this pass because spending authorization was not provided. Independent reviewers and prospective validators also require external coordination. Those are now the primary evidence blockers, not missing local orchestration plumbing.

## Fresh integration verification after the alignment changes

- `uv run pytest -q`: **431 passed**. The remaining PyMuPDF messages are upstream SWIG deprecation warnings, not failures.
- Web `npm test -- --run`: **8 files / 32 tests passed**.
- Web `npm run typecheck`: passed.
- Web `npm run build`: production build passed.
- `git diff --check` and Python bytecode compilation passed.
- A fresh deterministic smoke run with `--review-processes 2` produced four hypotheses, twelve reconciled reviews, durable worker-result artifacts, coordinator events, and a report. A subsequent `goal-revision` command was safety-approved and persisted goal/plan lineage.

These checks demonstrate implementation and integration integrity. They do not raise the demonstrated paper-level capability score because they contain no independent scientific-quality judgment or prospective coding-agent improvement result.

## Claim boundary

The project can currently claim: **"a paper-inspired, auditable coding-research supervisor with most major control-loop components and study infrastructure."**

It should not yet claim: **"a replication of Co-Scientist," "self-improving scientific capability," or "validated discovery quality."** Those statements require the external and empirical evidence listed above.
