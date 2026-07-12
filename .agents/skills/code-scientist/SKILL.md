---
name: code-scientist
description: Run the Code Scientist research engine for a user objective, generate host-agent subagent packets from the saved run state, spawn independent packet reviewers, and consolidate their findings. Also discovers candidate research objectives from a repository when the user has nothing specific in mind. Use when the user invokes code-scientist, asks for Code Scientist research, asks to find something to research, or wants Claude Code/Codex subagent orchestration over generated hypotheses.
---

# Code Scientist

## Overview

Use this skill as the operator entry point for the local Code Scientist package. The skill does not replace the Python supervisor; it runs the supervisor, converts the saved run into bounded packet files, delegates each packet to an independent host-agent subagent, then summarizes the subagent findings for the user.

Invoke explicitly in Codex with `$code-scientist` or through the skills picker. In Claude Code, the matching project skill is available as `/code-scientist`.

## Inputs

Treat `$ARGUMENTS` or the user's current request as the research objective unless the user points at an existing `runs/<run-id>/state.json`.

If the user supplies no objective, or asks to "find something to research", use discovery mode (Workflow step 2) to mine the repository for candidate objectives before running the engine.

## Run Levels

Pick the run level from the user's intent before choosing flags:

**Research-grade (default when the user wants real research, new ideas, or discoveries).** The deterministic provider assembles hypotheses from fixed blueprints — it can never produce a novel discovery. Legitimate new hypotheses require an LLM provider plus grounded evidence:

- Provider selection:
  1. Default: `--provider host-agent`. The engine routes every LLM call to this session through the run's file bridge (see "Host-Agent Bridge Loop" below) — you and your subagents are the model, with no API key and no extra login.
  2. `--provider anthropic` only when the user explicitly asks for an API-backed run. Never pick it just because `ANTHROPIC_API_KEY` happens to exist in the environment or `.env`.
  3. `--provider codex-cli` or `--provider claude-cli` when the user wants a detached or headless run: each provider call shells out to `codex exec` / `claude -p` using that CLI's own login. Confirm the binary answers first (an expired login fails with 401).
  4. If the user picked a provider explicitly, use it as given.
- Budgets: `--cycles 3 --max-hypotheses 10 --max-matches 8` (scale up if the user asks for depth; multiple cycles are required for the meta-review feedback loop to influence later generations). For host-agent runs add `--review-concurrency 3` so review requests arrive in batches you can fan out to subagents, and trim budgets (for example `--cycles 2 --max-hypotheses 8 --max-matches 4`) when the user wants a faster loop.
- Ground the run in real evidence — pass at least one of:
  - `--repo-search-path <path>` pointing at the code the objective concerns,
  - `--web-search-query "<objective keywords>"` (1-3 focused queries),
  - `--evidence-path <notes.md>` for local findings, or `--literature-search-query` for paper-style sourcing.
- Packet limit: `3`-`5`.
- `--pdf-vision` requires `--provider anthropic`; host-CLI providers cannot send image payloads.

**Smoke (only for wiring checks, demos, or when the user explicitly asks for a dry run).** Deterministic provider with `--cycles 1 --max-hypotheses 6 --max-matches 2` and packet limit `3`. Label the output as a deterministic dry run, never as research findings.

Run directory: `runs/<safe-objective-slug>`. Always use `uv` for Python commands.

## Host-Agent Bridge Loop (`--provider host-agent`)

The engine blocks each of its LLM calls on a file handshake that this session answers — the built-in agents are the model.

1. Start the run in the background (do not block waiting for it):
   - `uv run code-scientist run "<objective>" --provider host-agent --review-concurrency 3 <other flags> --out runs/<run-id>`
2. Loop until the run process exits:
   - List `runs/<run-id>/llm-bridge/requests/*.json`. Each file is one pending call; it disappears once the engine consumes its answer.
   - For each pending request, read its `id`, `prompt`, and `max_tokens`, produce the completion the prompt asks for, and write `runs/<run-id>/llm-bridge/responses/<id>.json` containing exactly `{"id": "<id>", "response": "<completion text>"}`.
   - Follow the prompt's requested output format precisely — usually bare JSON. Return raw text with no markdown fences and no commentary, sized within the request's `max_tokens`.
   - Answer short prompts inline. When several requests are pending at once (parallel reviews), spawn one subagent per request and write each response as it returns.
   - If a request cannot be answered, write `{"id": "<id>", "error": "<short reason>"}` so the engine fails that call cleanly instead of waiting on it.
   - If no requests are pending and the process is still running, wait briefly and poll again.
3. A request left unanswered for 600 seconds fails that engine call, so stay in the loop until the run process exits, then continue the workflow (report, packets, reviewers).

Budgets and stopping:

- `--provider-call-budget` (default 100) is a hard cap on the run's LLM calls; when exhausted, the engine finishes on its deterministic paths instead of asking for more answers. State the expected call ceiling to the user before starting a long run.
- To stop a run early, create `runs/<run-id>/llm-bridge/stop` — every pending and future bridge call fails immediately and the engine wraps up and writes `state.json` and `report.md`. Writing `{"action": "stop"}` to `runs/<run-id>/control.json` also stops any run at the next task boundary.
- After two consecutive unanswered requests the bridge declares itself abandoned and stops issuing calls, so a run whose operator walks away still finishes on its own.

## Workflow

1. Inspect the current state before running anything:
   - `git status --short --branch`
   - `uv run code-scientist --help`
2. Discovery mode — only when there is no objective yet:
   - `uv run code-scientist discover . --limit 5 --out runs/discovery/objective-candidates.json`
   - The command mines prior run overviews (`runs/*/state.json` next experiments and limitations), gap language in markdown docs, and TODO/FIXME comments, strongest signal first.
   - Present the numbered candidates with their sources and ask the user to pick one (or confirm the top candidate when the user asked you to just proceed). The chosen candidate's `objective` string becomes the research objective for the steps below.
   - If discovery returns nothing, say so and ask the user for an objective instead of inventing one.
3. If the user supplied an existing state file, skip directly to packet generation.
4. Otherwise run Code Scientist:
   - `uv run code-scientist run "<objective>" --provider host-agent --cycles <n> --max-hypotheses <n> --max-matches <n> --out runs/<run-id>`
   - For host-agent runs, start the command in the background and drive the Host-Agent Bridge Loop above until it exits.
   - Preserve user-supplied flags such as `--provider`, `--goal-brief`, `--evidence-path`, `--evidence-index`, `--repo-search-path`, `--web-search-query`, or `--continuous`.
5. Generate subagent packets:
   - `uv run code-scientist agent-packets runs/<run-id>/state.json --out runs/<run-id>/agent-packets --limit <n>`
6. Read `runs/<run-id>/agent-packets/packet-index.json`.
7. Spawn one independent subagent per packet. Prefer a project custom agent named `code-scientist-packet-reviewer` when available. If the host tool does not expose custom agents, spawn generic read-only reviewer subagents.
8. Give each subagent only the packet path or packet contents, not the entire `state.json`, unless it asks for a specific referenced id.
9. Wait for all subagents and consolidate:
   - top recommendation per packet,
   - disagreements or weak evidence,
   - highest-value next experiment or implementation step,
   - files and run artifacts created.

## Subagent Prompt Template

Use this shape for each spawned worker:

```text
Review this Code Scientist packet independently:
<packet path or packet markdown>

Return:
- Verdict: keep, revise, verify, or reject
- Key evidence: cite hypothesis, review, and evidence ids
- Main risk
- Next action

Do not edit source files. Keep the answer concise and grounded in the packet.
```

## Guardrails

- Keep `state.json` and `report.md` as the authoritative Code Scientist artifacts.
- Never present deterministic-provider hypotheses as new discoveries; they are blueprint-derived scaffolding.
- Do not mark generated hypotheses as validated unless benchmark, human-review, or prospective-validation artifacts prove it. A research-grade run produces *candidate* hypotheses; validation is a separate benchmark or implementation step.
- Do not let packet-review subagents modify source files unless the user separately asks for implementation.
- If implementing a selected hypothesis afterward, start a normal TDD implementation workflow instead of treating the research packet as proof.
- Preserve unrelated dirty worktree changes.
