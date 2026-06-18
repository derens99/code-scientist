# Code Scientist

Code Scientist is a local research engine inspired by the AI co-scientist paper. It generates, reviews, ranks, evolves, and reports testable hypotheses for improving AI coding agents, LLM workflows, prompts, memory, tool use, and evaluation design.

The MVP is offline and deterministic. It does not autonomously rewrite source code, deploy changes, or claim measured improvement without benchmark evidence.

## Usage

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
```
