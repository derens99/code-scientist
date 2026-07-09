# Code Scientist

Code Scientist is a local research engine inspired by the AI co-scientist paper. It generates, reviews, ranks, evolves, and reports testable hypotheses for improving AI coding agents, LLM workflows, prompts, memory, tool use, and evaluation design.

The default MVP path is offline and deterministic. It does not autonomously rewrite source code, deploy changes, or claim measured improvement without benchmark evidence.

The run state mirrors the paper's control loop with a parsed research plan configuration, paper-seeded evidence, generated and evolved hypotheses, structured reviews, Elo tournament matches, proximity graph edges, meta-reviews, and context-memory snapshots for scheduler/progress state.

## Usage

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
```

## Claude Code And Codex Agent Workflow

This repository includes project-scoped agent entry points:

- Claude Code: `.claude/skills/code-scientist/SKILL.md`, invoked as `/code-scientist`.
- Codex: `.agents/skills/code-scientist/SKILL.md`, invoked with `$code-scientist` or the skills picker.

The shared workflow runs Code Scientist, writes a normal `state.json` and `report.md`, converts top hypotheses into bounded subagent packets, then asks one independent read-only reviewer subagent to review each packet.

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
```

`packet-index.json` lists the generated packet files. The custom subagent definitions at `.claude/agents/code-scientist-packet-reviewer.md` and `.codex/agents/code-scientist-packet-reviewer.toml` are intentionally read-only: packet reviewers should return verdicts and next actions, not edit source files.

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

## Verified Local Demo

The MVP can be verified with:

```bash
uv run code-scientist run "Find testable ideas that could improve LLM coding agents" --cycles 2 --max-hypotheses 8 --max-matches 4 --out runs/demo
uv run code-scientist report runs/demo/state.json
```

The generated report separates hypotheses from verified improvements and labels Elo as an auto-evaluation proxy.
