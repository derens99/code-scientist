---
name: code-scientist
description: Run the Code Scientist research engine for a user objective, generate host-agent subagent packets from the saved run state, spawn independent packet reviewers, and consolidate their findings. Also discovers candidate research objectives from a repository when the user has nothing specific in mind. Use when the user invokes /code-scientist, asks for Code Scientist research, asks to find something to research, or wants Claude Code/Codex subagent orchestration over generated hypotheses.
---

# Code Scientist

## Overview

Use this skill as the operator entry point for the local Code Scientist package. The skill does not replace the Python supervisor; it runs the supervisor, converts the saved run into bounded packet files, delegates each packet to an independent host-agent subagent, then summarizes the subagent findings for the user.

Invoke this project skill in Claude Code as `/code-scientist`. In Codex, use the matching repo skill with `$code-scientist` or the skills picker.

## Inputs

Treat `$ARGUMENTS` or the user's current request as the research objective unless the user points at an existing `runs/<run-id>/state.json`.

If the user supplies no objective, or asks to "find something to research", use discovery mode (Workflow step 2) to mine the repository for candidate objectives before running the engine.

## Run Levels

Pick the run level from the user's intent before choosing flags:

**Research-grade (default when the user wants real research, new ideas, or discoveries).** The deterministic provider assembles hypotheses from fixed blueprints — it can never produce a novel discovery. Legitimate new hypotheses require the LLM provider plus grounded evidence:

- Confirm `ANTHROPIC_API_KEY` is available (environment or `.env`; the run command reads `--env-file .env` by default). If it is missing, say so and ask the user for it — do not silently fall back to deterministic and present the output as research.
- Run with `--provider anthropic`.
- Budgets: `--cycles 3 --max-hypotheses 10 --max-matches 8` (scale up if the user asks for depth; multiple cycles are required for the meta-review feedback loop to influence later generations).
- Ground the run in real evidence — pass at least one of:
  - `--repo-search-path <path>` pointing at the code the objective concerns,
  - `--web-search-query "<objective keywords>"` (1-3 focused queries),
  - `--evidence-path <notes.md>` for local findings, or `--literature-search-query` for paper-style sourcing.
- Packet limit: `3`-`5`.

**Smoke (only for wiring checks, demos, or when the user explicitly asks for a dry run).** Deterministic provider with `--cycles 1 --max-hypotheses 6 --max-matches 2` and packet limit `3`. Label the output as a deterministic dry run, never as research findings.

Run directory: `runs/<safe-objective-slug>`. Always use `uv` for Python commands.

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
   - `uv run code-scientist run "<objective>" --cycles <n> --max-hypotheses <n> --max-matches <n> --out runs/<run-id>`
   - Preserve user-supplied flags such as `--provider`, `--goal-brief`, `--evidence-path`, `--evidence-index`, `--repo-search-path`, `--web-search-query`, or `--continuous`.
5. Generate subagent packets:
   - `uv run code-scientist agent-packets runs/<run-id>/state.json --out runs/<run-id>/agent-packets --limit <n>`
6. Read `runs/<run-id>/agent-packets/packet-index.json`.
7. Spawn one independent subagent per packet. Prefer the project subagent named `code-scientist-packet-reviewer` when available. If the host tool does not expose custom agents, spawn generic read-only reviewer subagents.
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
