# Sample Run Output

This directory is the output of one deterministic run, committed so you can see
what Code Scientist produces before spending any tokens:

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" \
  --cycles 1 --max-hypotheses 6 --max-matches 2 --out runs/example-sample
uv run code-scientist agent-packets runs/example-sample/state.json \
  --out runs/example-sample/agent-packets --limit 2
uv run code-scientist findings runs/example-sample/state.json
```

- `state.json` — the full machine-readable run state (hypotheses, reviews,
  matches, proximity edges, meta-reviews, context snapshots).
- `report.md` — the comprehensive human-readable record.
- `findings.md` — the concise digest: ranked findings, rejections, next
  experiments, and limitations.
- `agent-packets/` — bounded packets for independent reviewer subagents.

Important labeling: this run used the default `deterministic` provider, so
every hypothesis is blueprint-derived scaffolding — useful for seeing the
artifact shapes and pipeline mechanics, never a source of novel research.
Research-grade runs use an LLM provider (`host-agent` inside Claude Code or
Codex, `anthropic`, `claude-cli`, or `codex-cli`) and grounded evidence flags;
see the Providers section of the repository README.
