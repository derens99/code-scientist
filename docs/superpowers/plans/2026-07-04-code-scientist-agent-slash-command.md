# Code Scientist Agent Slash Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested Code Scientist packet bridge plus project-scoped Claude Code and Codex skills that run the research engine and spawn read-only subagent packet reviewers.

**Architecture:** Keep the Python supervisor as the research engine. Add `agent-packets` as a deterministic CLI bridge from `RunState` to bounded markdown packets, then let host-agent skills perform subagent orchestration from those packets.

**Tech Stack:** Python 3.11+, `uv`, argparse CLI, Code Scientist dataclasses, Claude Code skills/subagents, Codex repo skills/custom agents, pytest.

---

## File Structure

- Create: `src/code_scientist/agent_packets.py` - packet selection, markdown rendering, and packet index writing.
- Modify: `src/code_scientist/cli.py` - `agent-packets` parser and command branch.
- Modify: `tests/test_cli.py` - regression test for packet generation.
- Create: `.claude/skills/code-scientist/SKILL.md` - Claude Code `/code-scientist` workflow.
- Create: `.agents/skills/code-scientist/SKILL.md` - Codex repo skill workflow.
- Create: `.claude/agents/code-scientist-packet-reviewer.md` - read-only Claude packet reviewer.
- Create: `.codex/agents/code-scientist-packet-reviewer.toml` - read-only Codex packet reviewer.
- Modify: `README.md` - operator usage docs.
- Create: `docs/superpowers/specs/2026-07-04-code-scientist-agent-slash-command-design.md` - design record.

## Task 1: Packet CLI Contract

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write the failing test**

Add `test_cli_agent_packets_writes_subagent_prompt_packets`, building a temporary `RunState` with one active hypothesis, one merged duplicate, one review, and one evidence record. Assert that `agent-packets` writes `packet-index.json`, emits one markdown packet for the active hypothesis, cites the review/evidence ids, and excludes the merged duplicate.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_agent_packets_writes_subagent_prompt_packets -q
```

Expected: fail with `invalid choice: 'agent-packets'`.

## Task 2: Packet Generator

**Files:**
- Create: `src/code_scientist/agent_packets.py`
- Modify: `src/code_scientist/cli.py`

- [x] **Step 1: Implement packet writing**

Create `write_agent_packets(...)` and `render_agent_packet(...)`. Select active hypotheses by research-overview top order and Elo, exclude `merged_duplicate`, resolve evidence refs from hypotheses and reviews, write one markdown packet per selected hypothesis, and write `packet-index.json`.

- [x] **Step 2: Wire the CLI**

Add parser:

```bash
code-scientist agent-packets <state.json> --out <packet-dir> --limit 3
```

Load state with `load_state(...)`, call `write_agent_packets(...)`, print written paths, and return `0`.

- [x] **Step 3: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_cli.py::test_cli_agent_packets_writes_subagent_prompt_packets -q
```

Expected: pass.

## Task 3: Claude And Codex Entry Points

**Files:**
- Create: `.claude/skills/code-scientist/SKILL.md`
- Create: `.agents/skills/code-scientist/SKILL.md`
- Create: `.claude/agents/code-scientist-packet-reviewer.md`
- Create: `.codex/agents/code-scientist-packet-reviewer.toml`

- [x] **Step 1: Initialize skill directories**

Run:

```bash
uv run python ~/.codex/skills/.system/skill-creator/scripts/init_skill.py code-scientist --path .agents/skills --interface display_name="Code Scientist" --interface short_description="Run Code Scientist and orchestrate subagent review packets." --interface default_prompt="Use Code Scientist to research this objective and spawn packet reviewers."
uv run python ~/.codex/skills/.system/skill-creator/scripts/init_skill.py code-scientist --path .claude/skills --interface display_name="Code Scientist" --interface short_description="Run Code Scientist and orchestrate subagent review packets." --interface default_prompt="Use Code Scientist to research this objective and spawn packet reviewers."
```

- [x] **Step 2: Replace templates**

Write the skill workflow:

- inspect `git status --short --branch`,
- run `uv run code-scientist run ...`,
- run `uv run code-scientist agent-packets ...`,
- read `packet-index.json`,
- spawn one read-only packet reviewer subagent per packet,
- consolidate verdicts and next actions.

- [x] **Step 3: Add packet reviewer agents**

Add one Claude subagent markdown file and one Codex custom-agent TOML file. Both must require read-only packet review and the same response shape: verdict, key evidence, main risk, next action.

## Task 4: Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/specs/2026-07-04-code-scientist-agent-slash-command-design.md`
- Create: `docs/superpowers/plans/2026-07-04-code-scientist-agent-slash-command.md`

- [x] **Step 1: Add README usage**

Document `.claude/skills/code-scientist/SKILL.md`, `.agents/skills/code-scientist/SKILL.md`, and the exact `uv run code-scientist agent-packets ...` command.

- [x] **Step 2: Save design and plan**

Record architecture, data flow, guardrails, verification, and non-goals.

## Task 5: Verification

**Files:**
- No code changes.

- [x] **Step 1: Run backend tests**

Run:

```bash
uv run pytest -q
```

Observed: `303 passed`.

- [x] **Step 2: Validate skill metadata**

Run:

```bash
uv run python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/code-scientist
uv run python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .claude/skills/code-scientist
```

Observed: both validations passed with `uv run --with pyyaml ...` because the validator imports PyYAML.

- [x] **Step 3: Run a real smoke**

Run:

```bash
uv run code-scientist run "Find testable ideas to improve coding-agent subagent orchestration" --cycles 1 --max-hypotheses 3 --max-matches 1 --out runs/slash-command-smoke
uv run code-scientist agent-packets runs/slash-command-smoke/state.json --out runs/slash-command-smoke/agent-packets --limit 2
```

Observed: `state.json`, `report.md`, `agent-packets/packet-index.json`, and two packet markdown files were written.

- [x] **Step 4: Check formatting and worktree**

Run:

```bash
git diff --check
git status --short --branch
```

Observed: `git diff --check` passed. Worktree status still includes pre-existing dirty changes plus the new integration files.
