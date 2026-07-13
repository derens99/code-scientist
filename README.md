# Code Scientist

Code Scientist is a local research engine inspired by the AI co-scientist paper. It generates, reviews, ranks, evolves, and reports testable hypotheses for improving AI coding agents, LLM workflows, prompts, memory, tool use, and evaluation design.

The default MVP path is offline and deterministic. It does not autonomously rewrite source code, deploy changes, or claim measured improvement without benchmark evidence.

The run state mirrors the paper's control loop with a parsed research plan configuration, paper-seeded evidence, generated and evolved hypotheses, structured reviews, Elo tournament matches, proximity graph edges, meta-reviews, and context-memory snapshots for scheduler/progress state.

## Quickstart

Requirements: Python 3.11+ managed with [uv](https://docs.astral.sh/uv/). Node 22 is only needed for the optional web workbench. Claude Code or Codex is only needed for research-grade `host-agent` runs.

```bash
git clone https://github.com/derens99/code-scientist.git && cd code-scientist
uv sync
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
uv run code-scientist findings runs/demo/state.json
```

That first run is offline and deterministic — no API key, no login — and shows the full pipeline and artifact shapes in under a minute. [examples/sample-run](examples/sample-run) is a committed copy of exactly this output. Deterministic hypotheses are blueprint scaffolding, never novel research.

For research-grade runs, open this repository in Claude Code and invoke `/code-scientist` (or `$code-scientist` in Codex) with your research objective. The skill defaults to `--provider host-agent`, where the agent session itself answers the engine's LLM calls — no API key involved. See Providers below for the API and headless-CLI alternatives.

To research one of your own projects, run from this checkout and point the evidence flags at your code:

```bash
uv run code-scientist run "How should <your project> reduce <problem>?" \
  --provider host-agent \
  --repo-search-path /path/to/your/project \
  --out runs/your-project-question
```

## Web Workbench

`web/` contains a Next.js workbench for configuring and starting runs, watching progress, inspecting hypotheses, reviews, evidence, and the proximity graph, and sending human guidance (goal revisions, safety approvals, source attachments, evaluation returns) to a running supervisor:

```bash
cd web
npm install
npm run dev
```

The workbench shells out to `uv run code-scientist` in the repository root (override with `CODE_SCIENTIST_ROOT`) and lists run directories under `runs/`.

The workbench binds to `127.0.0.1` by default. File inputs are confined to the
repository root plus optional roots in `CODE_SCIENTIST_ALLOWED_ROOTS` (separated
with the platform path delimiter). Direct web evidence and agent fetch domains
must be explicitly allowlisted with a comma-separated
`CODE_SCIENTIST_ALLOWED_FETCH_DOMAINS`. Mutating API routes reject cross-origin
browser requests. These controls harden local use; they do not turn the
workbench into an authenticated multi-user service.

## Providers

`--provider` selects who answers the engine's LLM calls:

- `deterministic` (default): offline blueprint scaffolding; no network and no key, but never a source of novel hypotheses.
- `anthropic`: the Anthropic API. Requires `ANTHROPIC_API_KEY` in the environment or the `--env-file` file.
- `claude-cli`: shells each provider call out to headless Claude Code (`claude -p --model <model> --output-format text`). Reuses the local `claude` login, so research-grade runs work with no API key — this is what `/code-scientist` uses inside Claude Code when no key is configured.
- `codex-cli`: shells each provider call out to `codex exec` in a read-only sandbox, reading the reply from `--output-last-message`. Reuses the local `codex` login. `--model` keeps its Anthropic default, which this provider treats as "use the codex CLI's configured model"; pass an explicit Codex model id to override.
- `host-agent`: blocks each provider call on a file handshake with the agent session that launched the run — the built-in Claude Code/Codex agents are the model, with no API key or separate login. The engine writes `runs/<run-id>/llm-bridge/requests/<id>.json` (`{"id", "prompt", "max_tokens", "created_at"}`) and waits up to 600 seconds for `runs/<run-id>/llm-bridge/responses/<id>.json` containing `{"id", "response"}` (or `{"id", "error"}` to fail that call). Answered request files are removed, so `requests/` always lists exactly the pending calls; wrapping code fences in responses are stripped. This is the `/code-scientist` skill's default for research-grade runs.

Host-CLI providers spawn one headless agent per call, so runs are slower than API runs. Neither host-CLI nor host-agent providers accept image payloads, so `--pdf-vision` remains `anthropic`-only, and `host-agent` runs execute reviews in-process (`--review-processes` is rejected because detached workers cannot reach the answering session).

Host-CLI children receive an allowlisted environment rather than the full parent environment: path/home, locale, temporary-directory, proxy, certificate, XDG, and provider config-directory variables are preserved. Ambient API keys, tokens, passwords, and unrelated service variables are not inherited. The measured Claude executor passes `ANTHROPIC_API_KEY` only in explicit `--agent-auth api-key` mode after loading it from `--env-file`.

Run controls: `--provider-call-budget` (default 100) is a hard in-process cap on LLM calls for every provider — on exhaustion, agents fall back to their deterministic paths and the run finishes instead of spending more. Creating `runs/<run-id>/llm-bridge/stop` cancels a host-agent run immediately (pending and future bridge calls fail and the engine drains to `state.json`/`report.md`), `{"action": "stop"}` in `runs/<run-id>/control.json` stops any run at the next task boundary, and a bridge with two consecutive unanswered requests declares itself abandoned so orphaned runs terminate on their own.

```bash
uv run code-scientist run "Find testable ideas to improve coding-agent subagent orchestration" \
  --provider host-agent \
  --review-concurrency 3 \
  --cycles 2 \
  --max-hypotheses 8 \
  --repo-search-path src \
  --out runs/host-agent-demo
```

## Claude Code And Codex Agent Workflow

This repository includes project-scoped agent entry points:

- Claude Code: `.claude/skills/code-scientist/SKILL.md`, invoked as `/code-scientist`.
- Codex: `.agents/skills/code-scientist/SKILL.md`, invoked with `$code-scientist` or the skills picker.

The shared workflow runs Code Scientist, writes a normal `state.json` and `report.md`, converts top hypotheses into bounded subagent packets, then asks one independent read-only reviewer subagent to review each packet. Research-grade runs default to `--provider host-agent`: the skill starts the engine in the background and the host session answers the run's `llm-bridge` requests itself (fanning out to subagents for parallel batches), so no API key is involved. `--provider anthropic` is used only when the operator explicitly asks for the API, and `claude-cli`/`codex-cli` remain for detached headless automation.

When the operator has no objective yet, discovery mode mines the repository for candidates first — prior run overviews (`runs/*/state.json` next experiments and limitations), gap language in markdown docs, and TODO/FIXME comments, ranked strongest signal first:

```bash
uv run code-scientist discover . --limit 5 --out runs/discovery/objective-candidates.json
```

The command prints numbered candidates with their provenance and writes the same list as JSON; the chosen candidate's `objective` string feeds the normal run:

```bash
uv run code-scientist run "Find testable ideas to improve coding-agent subagent orchestration" \
  --cycles 1 \
  --max-hypotheses 6 \
  --max-matches 2 \
  --out runs/subagent-orchestration

uv run code-scientist agent-packets runs/subagent-orchestration/state.json \
  --out runs/subagent-orchestration/agent-packets \
  --limit 3

uv run code-scientist findings runs/subagent-orchestration/state.json
```

`packet-index.json` lists the generated packet files. `findings` writes `findings.md` next to the state file — a concise digest of the ranked findings (claim, review strengths and risks, suggested experiment), what was rejected in review and why, recommended next experiments, missing evidence, and limitations. When the host saves packet-reviewer verdicts to `agent-packets/reviews/<hypothesis-id>.md`, each finding also carries its independent reviewer verdict; `report.md` remains the comprehensive record. The custom subagent definitions at `.claude/agents/code-scientist-packet-reviewer.md` and `.codex/agents/code-scientist-packet-reviewer.toml` are intentionally read-only: packet reviewers should return verdicts and next actions, not edit source files.

## Benchmark Fixtures

Use `--benchmark-fixture` to attach measured baseline and candidate metrics to a run:

```json
{
  "name": "Seeded workflow comparison",
  "baseline": {
    "pass_rate": 0.5,
    "regression_count": 3,
    "tool_calls": 20,
    "wall_time": 12.5,
    "cost": 0.4
  },
  "candidate": {
    "pass_rate": 0.75,
    "regression_count": 1,
    "tool_calls": 18,
    "wall_time": 10.0,
    "cost": 0.25
  },
  "notes": ["Fixture comes from a local smoke benchmark."]
}
```

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --benchmark-fixture benchmark.json --out runs/benchmarked-demo
```

Fixtures are asserted evidence: the engine records the metrics you supply and labels their provenance accordingly. For metrics the engine itself executes, see Measured Validation.

## Measured Validation

`code-scientist validate` closes the loop the fixtures leave open: it takes one hypothesis from a saved state and runs it as a pre-registered, paired, baseline-vs-candidate experiment on a real coding agent. Both arms solve the same tasks from [benchmarks/agent-tasks](benchmarks/agent-tasks) under identical limits; the only difference is the candidate arm's appended system prompt (the intervention derived from the hypothesis). Each trial arm gets a fresh copy of the task workspace, and held-out grader tests — never visible to the agent — are copied in afterwards and decide pass/fail.

```bash
uv run code-scientist validate runs/my-run/state.json \
  --hypothesis hyp-xxxxxxxxxxxx \
  --intervention-file intervention.txt \
  --executor host-agent \
  --trials 3 --trial-concurrency 4 \
  --out runs/my-run/experiments/hyp-xxxxxxxxxxxx
```

The protocol (intervention text, task ids, trials, seed, model, limits, decision rule, cost budget) is written to `protocol.json` and hashed before the first trial runs; `--dry-run` stops there. Results embed the protocol hash, so a result can always be checked against what was registered, and a completed experiment directory is never silently overwritten.

Executors:

- `host-agent` (no API key): the experiment analogue of the host-agent provider. The engine posts whole trial batches to `<experiment>/agent-bridge/requests/<id>.json` — each request carries the complete trial input (`prompt`, `system_append`, `workspace`, `timeout_seconds`) — and the launching session runs each request as a fresh subagent from a fixed template, writing `responses/<id>.json` with `{"id", "status", "duration_seconds", "num_turns", "cost_usd"}`. Answered requests are removed, `agent-bridge/stop` cancels, and two consecutive fully-unanswered batches abandon the run.
- `claude-cli`: one headless Claude Code process per trial arm (`claude -p --output-format json --max-turns N [--append-system-prompt ...]`) with cwd set to the trial workspace. `--agent-auth login` reuses the local CLI login; `--agent-auth api-key` passes the key from `--env-file` explicitly (session-injected proxy variables are never trusted).
- `deterministic`: offline scripted scaffolding for tests and demos, like every other deterministic path.

The primary analysis is pre-registered: a one-sided exact McNemar test over discordant (task, trial) pairs at the registered alpha, with a minimum-discordant-pairs floor below which the verdict is `inconclusive` regardless of the point estimate. A seeded bootstrap CI on the pass-rate delta and a task-level sign test (robustness against within-task clustering) are reported alongside. Verdicts are `supported`, `refuted`, `inconclusive`, or `incomplete` (budget stop or abort) — never a bare point estimate. The measured `BenchmarkResult` lands in `state.json` with `provenance: measured:agent-experiment`, its verdict and stats attached, and `report.md`/`findings.md` display it as executed evidence, distinct from asserted fixtures. Execution policy is `trusted_local`, the same honesty contract as `prospective-validation-run`: trials run as local subprocesses in temporary workspace copies and no sandbox isolation is claimed.

An overtime rule gives soft-enforcement executors real timeout semantics: an arm that reports more wall time than the trial budget fails even if the graders pass, deterministically for both arms.

[examples/measured-validation-study](examples/measured-validation-study) is a complete committed run of this pipeline: a host-agent engine run generated and tournament-ranked a prompt-intervention hypothesis, an independent packet reviewer forced protocol fixes, three instrument designs calibrated to ceiling before composite task bundles restored headroom, and the pre-registered experiment (24 pairs, 48 agent trials) returned an honest `inconclusive` with a negative point estimate — the intervention cost +32% wall time and won 1 of 6 discordant pairs. The pipeline's value is that this claim died in measurement instead of shipping as a plausible Elo-ranked finding.

## Grounded Evidence Reviews

Use `--goal-brief` to attach researcher-supplied planning briefs before a run starts. Briefs can include Markdown sections such as `Preferences`, `Constraints`, `Metrics`, `Safety notes`, `Allowed sources`, `Allowed tools`, `Output formats`, and `Termination criteria`; those sections augment the persisted goal and derived research plan. When a brief provides explicit allowed sources or tools, requested evidence collectors that do not match the plan are skipped and recorded as source-policy findings in the run's evidence safety review.

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" \
  --goal-brief notes/research-brief.md \
  --out runs/briefed-demo
```

Use `--safety-policy` to attach organization-specific safety rules before goal and evidence screening. Policy files are JSON and contain `rules` with an `id`, `scope` list, `contains` terms or regex `patterns`, and a reviewer-facing `reason`:

```json
{
  "name": "local research boundaries",
  "rules": [
    {
      "id": "restricted-corpus",
      "scope": ["goal", "evidence"],
      "contains": ["restricted incident corpus"],
      "reason": "Restricted incident corpus requires separate approval."
    },
    {
      "id": "obfuscated-injection",
      "scope": ["evidence"],
      "patterns": ["ignore\\s+(?:all\\s+)?previous\\s+instructions"],
      "reason": "Obfuscated prompt-injection instructions are not allowed."
    }
  ]
}
```

Use `--evidence-path` to attach local notes, benchmark summaries, source files, or small corpora to a run. The supervisor ingests supported text files and uses grounded full reviews to flag hypotheses contradicted by local evidence before they enter the tournament.

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" \
  --goal-brief notes/research-brief.md \
  --safety-policy notes/safety-policy.json \
  --evidence-path notes/agent-failures.md \
  --out runs/grounded-demo
```

Use `--repo-search-path` for cited local repository search evidence, `--web-evidence-url` for explicit HTTP(S) documents that should be fetched and cited as web evidence with capped `web_document_span` citations, `--web-crawl-depth` to follow same-origin links from explicit web evidence URLs, `--web-search-query` for cited Bing RSS search-result evidence, and `--literature-search-query` for gated OpenAlex literature search results. Add `--web-search-fetch` to fetch the result pages from web search as cited `web_search_document` evidence plus screened `web_search_document_span` citations, add `--web-search-crawl-depth` to follow same-origin links from those fetched search-result pages, and add `--literature-full-text` to follow OpenAlex open-access URLs and attach cited `literature_full_text` evidence plus capped `literature_full_text_span` citations. Retrieved evidence is screened before agents can cite it.

Add `--agent-retrieval --tool-budget N` when Generation and Reflection should formulate and refine their own queries instead of collecting only the researcher-supplied seed queries before the run. Agent retrieval is limited to explicitly configured repository paths and enabled web/literature channels. After observing a web or OpenAlex result, an agent may request its document/full text by evidence `source_ref`; it never supplies a URL. The executor enforces public HTTP(S), safe ports and redirects, blocks private/link-local targets, and accepts repeatable `--agent-fetch-domain` allowlist entries. The budget is a hard run-wide limit for the current supervisor process: failed calls consume it, concurrent in-process retrieval tasks cannot overspend it, and usage is persisted for resume. Retrieval calls are not yet coordinated across independently launched processes. `--agent-retrieval-iterations N` sets the per-task observation/refinement ceiling from one to ten; duplicate or unproductive iterations stop early and the shared budget still wins. Agents cannot select filesystem roots, arbitrary URLs, domains, crawling, full-text settings, or shell commands.

Add one or more `--agent-validation-manifest path.json` arguments when Reflection should execute researcher-owned empirical checks in-loop. These manifests use the same command-list, no-shell contract as prospective validation, receive the current hypothesis through `CODE_SCIENTIST_HYPOTHESIS_PATH`, and return measured metrics through `CODE_SCIENTIST_METRICS_PATH` or JSON stdout. Every attempted execution reserves one unit from the same hard tool budget before the process starts. The agent selects neither the command nor its working directory. Study manifests can provide per-goal `agent_validation_manifests` paths, resolved relative to the study manifest. Host execution uses a minimal environment, blocks secret-like manifest variables, constrains the working directory, applies resource limits, captures bounded output, and terminates the process group on timeout. It is explicitly attested as `host_restricted_not_sandboxed`: network isolation requires an external container or VM runner, and `execution_policy: hardened` fails closed until one is configured.

Each run persists a dependency-aware cross-kind task graph in both atomic `state.json` and a SQLite WAL coordinator. Transactional claims enforce dependencies and resource-class capacity; leases, heartbeats, expired-worker recovery, named SQLite budgets, and append-only coordinator events are process-safe. The default scheduler stays in-process. Add `--review-processes N` to execute portable review packets in separate lease-based processes for deterministic or explicitly selected Anthropic runs. Provider packets contain digests and bounded review inputs, never credentials or environment-file authority; workers receive provider authority from operator-owned runtime flags and consume an atomic `--provider-call-budget` before every request. Expired provider packets fail for manual review rather than replaying a potentially billable call. `code-scientist worker RUN_DIR` runs a packet worker and `code-scientist coordination-status RUN_DIR` prints the durable task/event view.

Every state write also appends newly observable events to `activity.jsonl`. The ledger uses stable event ids and monotonic sequence numbers to preserve task transitions, agent tool calls, goal/evidence safety decisions, source ingestions, run-status changes, and human feedback without rewriting prior history. Tournament ranking performs an order-swap audit for each A/B pair; A/B versus B/A disagreement is recorded and converted to an Elo-preserving abstention.

Run the built-in safety suite together with loadable coding-domain corpora using `safety-red-team`. Corpus files contain a `cases` list with `id`, `topic`, `subject_type` (`goal`, `hypothesis`, or `evidence`), `objective`, `expected_allowed`, and optional `paraphrases` / `obfuscations`. `--generate-variants` creates one deterministic paraphrase and obfuscation per base case and reports per-topic pass rates plus base-to-variant degradation instead of hiding weak robustness behind a single aggregate.

```bash
uv run code-scientist safety-red-team \
  --corpus evaluation/safety-corpus.json \
  --generate-variants \
  --out runs/safety-red-team.json
```

```bash
uv run code-scientist run "Find web-grounded ideas for LLM coding agents" \
  --web-evidence-url https://example.com/research-note \
  --web-crawl-depth 1 \
  --web-search-query "swebench.com benchmark GitHub issues language models" \
  --web-search-fetch \
  --web-search-crawl-depth 1 \
  --literature-search-query "coding agent benchmark" \
  --literature-full-text \
  --out runs/web-grounded-demo
```

```bash
uv run code-scientist run "Find iteratively grounded ideas for LLM coding agents" \
  --repo-search-path . \
  --web-search-query "coding agent benchmark reliability" \
  --literature-search-query "LLM coding agent evaluation" \
  --agent-retrieval \
  --agent-fetch-domain arxiv.org \
  --tool-budget 12 \
  --out runs/agent-retrieval-demo
```

PDF attachments use native page text first, then real RapidOCR/ONNX extraction for scanned pages. OCR evidence records page numbers, confidence, and PDF-coordinate text boxes. PyMuPDF table and image inspection also records cited table cells, figure/page-scan bounding boxes, image references, and nearby captions. By default, figure regions remain provenance-only records. With an explicitly selected Anthropic provider and `--pdf-vision`, the supervisor renders only bounded figure crops, spends from `--pdf-vision-call-budget`, validates a structured interpretation, and creates claim-level `pdf_visual_claim` evidence linked to the source page, bounding box, crop hash, and model. These claims are always marked machine-interpreted and require human verification.

```bash
uv run code-scientist run "Find robust coding-agent recovery ideas" \
  --evidence-path papers/scanned-study.pdf \
  --review-processes 3 \
  --out runs/process-review-demo

uv run code-scientist coordination-status runs/process-review-demo
```

```bash
uv run code-scientist run "Interpret attached coding-agent study figures" \
  --provider anthropic \
  --evidence-path papers/study.pdf \
  --pdf-vision \
  --pdf-vision-max-regions 6 \
  --pdf-vision-call-budget 6 \
  --out runs/vision-grounded-demo
```

Goal guidance can revise the objective, constraints, metrics, source/tool allowlists, output formats, and termination criteria. Revisions are safety-reviewed, get new goal/plan identities, supersede only queued/deferred work, and preserve completed artifacts. The workbench exposes this form. The CLI queues revisions for a running supervisor to consume at a cycle boundary and applies them immediately to completed/stopped runs:

```bash
uv run code-scientist goal-revision runs/demo \
  --patch-json '{"constraints":["Use public benchmarks only"],"metrics":["pass_rate","cost"]}' \
  --message "Narrow the next research cycle"
```

```bash
uv run code-scientist run "Find empirically testable coding-agent improvements" \
  --agent-validation-manifest validation/benchmark-probe.json \
  --tool-budget 8 \
  --out runs/agent-validation-demo
```

Build reusable local corpus indexes with `code-scientist index`, then attach them to later runs with `--evidence-index`. Local and indexed evidence retrieval uses BM25-style term-frequency ranking plus a deterministic local embedding fallback for hybrid private-corpus retrieval. Citations include markdown section paths and PDF page numbers when available:

```bash
uv run code-scientist index \
  --evidence-path notes/agent-failures.md \
  --name "agent failure corpus" \
  --out indexes/agent-failures.index.json

uv run code-scientist run "Find corpus-grounded ideas for LLM coding agents" \
  --evidence-index indexes/agent-failures.index.json \
  --out runs/indexed-grounded-demo
```

Use `--capability-eval-fixture` to attach external baseline, human, or benchmark judgment scores to the hypotheses produced by a run. Fixtures can score exact hypothesis ids or use keyword rules that match hypothesis text:

```json
{
  "baseline_name": "single_shot_llm",
  "baseline_score": 0.45,
  "human_scores": {
    "hyp-example": 0.7
  },
  "human_score_rules": [
    { "contains": "failure replay", "score": 0.8 }
  ],
  "benchmark_score_rules": [
    { "contains": ["SWE-bench", "pass rate"], "score": 0.75 }
  ]
}
```

## Paper-Style Capability Study Kit

Use `paper-study-kit` to write a local, runnable starter study with multiple coding-agent research goals, benchmark suites, safety red-team activation, and reviewer templates:

```bash
uv run code-scientist paper-study-kit --out tmp/paper-study-kit
uv run code-scientist study-run tmp/paper-study-kit/study-manifest.json --out runs/paper-study-local
uv run code-scientist paper-study-materials runs/paper-study-local --out runs/paper-study-local/materials --seed paper-study
uv run code-scientist prospective-validation-run runs/paper-study-local/failure-replay-small/state.json validation-manifest.json --work-dir runs/paper-study-local/prospective-work --out runs/paper-study-local/returned-prospective-validation.json
uv run code-scientist capability-review-fixture runs/paper-study-local/materials/review/capability-review-score-template.json --answer-key runs/paper-study-local/materials/review/capability-review-answer-key.json --out runs/paper-study-local/returned-capability-review.json --human-rubric-scale 5
uv run code-scientist preference-review-fixture runs/paper-study-local/materials/review/preference-review-template.json --answer-key runs/paper-study-local/materials/review/preference-review-answer-key.json --out runs/paper-study-local/returned-preference-review.json
uv run code-scientist feedback-loop-review-fixture runs/paper-study-local/materials/review/score-template.json --answer-key runs/paper-study-local/materials/review/answer-key.json --out runs/paper-study-local/returned-feedback-review.json
uv run code-scientist study runs/paper-study-local/*/state.json --out runs/paper-study-local/study-audit.md
```

The generated kit gives the paper-style evaluation path concrete local artifacts. `paper-study-materials` turns completed study-run states into populated blinded review packets, private answer keys, score/preference templates, and per-hypothesis prospective validation templates. `prospective-validation-run` executes a no-shell command-list manifest against a selected saved-state hypothesis and writes an ingestion-ready measured prospective fixture; `study-run` can also execute global or per-goal `prospective_validation_manifests` and append those measured results to each goal state. The review fixture commands merge reviewer-returned rubric scores, blind preferences, and feedback-loop scores with private answer keys into ingestion-ready review fixtures. It still requires real human rubric scores, real human preference choices, real prospective validation measurements, and external feedback-loop review scores before the study should be treated as paper-level validation.

## Continuous Runs

Use `--continuous` when you want the supervisor to keep generating, reviewing, ranking, evolving, and writing context memory:

```bash
uv run code-scientist run "Research non-transformer language models that run on laptop compute" \
  --provider anthropic \
  --continuous \
  --interval-seconds 60 \
  --max-wall-minutes 120 \
  --out runs/non-transformer-continuous
```

Continuous runs write `state.json` before the first cycle, update `report.md` after each cycle, and resume from an existing `state.json` in the same output directory. The workbench can pause, resume, or stop a run by writing `control.json`; the CLI loop reads that file between cycles.

## Anthropic Haiku Provider

The deterministic provider remains the default. To generate hypotheses with Claude Haiku, place your API key in `.env`:

```bash
ANTHROPIC_API_KEY=your-key-here
```

Then run:

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --provider anthropic --model claude-haiku-4-5 --cycles 1 --max-hypotheses 4 --out runs/haiku-demo
```

`.env` is ignored by git. Do not commit real API keys.

## Development

```bash
uv sync                  # install the engine and dev dependencies
uv run pytest -q         # Python test suite
uvx ruff check src tests # lint

cd web
npm install
npm test                 # web test suite
npm run typecheck
npm run build
```

Design notes and implementation plans live in `docs/`, including the paper-alignment audits that track how closely the engine reproduces the co-scientist paper's mechanisms.

## Known Limitations

- Hypotheses are candidates, not validated results. Reviews, Elo, and the findings digest are auto-evaluation proxies; the reports label them as such. `code-scientist validate` can attach a measured verdict to a specific hypothesis, but that verdict is scoped to the experiment's task suite, model, and limits — every hypothesis without one remains an unvalidated candidate.
- The agent-task suite is small (10 tasks) and stdlib-only; measured experiments on it detect large effects, not subtle ones, and pair-level McNemar is mildly anticonservative under within-task clustering (the task-level sign test is reported as the robustness check).
- Reviews within one run usually share a single judge (the session model answering the bridge, or one API model), so cross-review agreement cannot certify correctness. Independent packet-reviewer subagents mitigate but do not remove this.
- `codex exec` can hang when invoked from inside another agent's sandbox; use `--provider codex-cli` from a normal shell. `claude-cli` fails with 401 when the standalone `claude` login has expired — run `claude /login` first.
- `--pdf-vision` requires `--provider anthropic`; host-CLI and host-agent providers cannot carry image payloads.
- Host-agent runs depend on the launching session staying attentive; unanswered bridge requests time out after 600 seconds and two consecutive timeouts end the run's LLM phase (deterministic paths finish the run).
- Developed and tested on macOS and Linux (CI); Windows is untested.

## License

MIT. See [LICENSE](LICENSE).

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Please report
security issues privately as described in [SECURITY.md](SECURITY.md).
