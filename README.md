# Code Scientist

Code Scientist is a local research engine inspired by the AI co-scientist paper. It generates, reviews, ranks, evolves, and reports testable hypotheses for improving AI coding agents, LLM workflows, prompts, memory, tool use, and evaluation design.

The default MVP path is offline and deterministic. It does not autonomously rewrite source code, deploy changes, or claim measured improvement without benchmark evidence.

The run state mirrors the paper's control loop with a parsed research plan configuration, paper-seeded evidence, generated and evolved hypotheses, structured reviews, Elo tournament matches, proximity graph edges, meta-reviews, and context-memory snapshots for scheduler/progress state.

## Usage

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
```

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
