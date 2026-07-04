---
name: code-scientist
description: Run the Code Scientist research engine for a user objective, generate host-agent subagent packets from the saved run state, spawn independent packet reviewers, and consolidate their findings. Use when the user invokes code-scientist, asks for Code Scientist research, or wants Claude Code/Codex subagent orchestration over generated hypotheses.
---

# Code Scientist

## Overview

Use this skill as the operator entry point for the local Code Scientist package. The skill does not replace the Python supervisor; it runs the supervisor, converts the saved run into bounded packet files, delegates each packet to an independent host-agent subagent, then summarizes the subagent findings for the user.

Invoke explicitly in Codex with `$code-scientist` or through the skills picker. In Claude Code, the matching project skill is available as `/code-scientist`.

## Inputs

Treat `$ARGUMENTS` or the user's current request as the research objective unless the user points at an existing `runs/<run-id>/state.json`.

Use conservative defaults when the user does not specify run options:

- Run directory: `runs/<safe-objective-slug>`.
- Cycles: `1`.
- Max hypotheses: `6`.
- Max matches: `2`.
- Packet limit: `3`.
- Provider: deterministic unless the user explicitly requests Anthropic.

Always use `uv` for Python commands.

## Workflow

1. Inspect the current state before running anything:
   - `git status --short --branch`
   - `uv run code-scientist --help`
2. If the user supplied an existing state file, skip directly to packet generation.
3. Otherwise run Code Scientist:
   - `uv run code-scientist run "<objective>" --cycles <n> --max-hypotheses <n> --max-matches <n> --out runs/<run-id>`
   - Preserve user-supplied flags such as `--provider`, `--goal-brief`, `--evidence-path`, `--evidence-index`, `--repo-search-path`, `--web-search-query`, or `--continuous`.
4. Generate subagent packets:
   - `uv run code-scientist agent-packets runs/<run-id>/state.json --out runs/<run-id>/agent-packets --limit <n>`
5. Read `runs/<run-id>/agent-packets/packet-index.json`.
6. Spawn one independent subagent per packet. Prefer a project custom agent named `code-scientist-packet-reviewer` when available. If the host tool does not expose custom agents, spawn generic read-only reviewer subagents.
7. Give each subagent only the packet path or packet contents, not the entire `state.json`, unless it asks for a specific referenced id.
8. Wait for all subagents and consolidate:
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
- Do not mark generated hypotheses as validated unless benchmark, human-review, or prospective-validation artifacts prove it.
- Do not let packet-review subagents modify source files unless the user separately asks for implementation.
- If implementing a selected hypothesis afterward, start a normal TDD implementation workflow instead of treating the research packet as proof.
- Preserve unrelated dirty worktree changes.
