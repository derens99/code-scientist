# Code Scientist Design

## Purpose

Build a local "Code Scientist" system that adapts the architecture from `2502.18864.pdf`, "Towards an AI co-scientist", to computer science, AI, and LLM improvement research.

The system should help LLMs automatically research new ideas that could improve AI coding agents, LLM workflows, prompts, tool use, memory, evaluation design, and repo-level engineering behavior. It should generate, critique, rank, evolve, and report testable improvement hypotheses while preserving evidence and human oversight.

## Paper Analysis

The paper's core contribution is not merely a collection of agents. Its useful mechanism is a controlled research loop:

1. Parse a natural-language research goal into a plan configuration.
2. Generate multiple candidate hypotheses.
3. Review candidates for alignment, plausibility, novelty, testability, and safety.
4. Compare candidates through pairwise tournament matches.
5. Maintain an Elo-style ranking to allocate more compute to promising candidates.
6. Evolve strong candidates into new variants without overwriting originals.
7. Use meta-review to find recurring critique patterns and feed them into later agent prompts.
8. Persist state, evidence, critiques, tournament outcomes, and final research overviews.

For Code Scientist, "scientific hypotheses" become structured CS/AI improvement hypotheses. A hypothesis is not accepted because an LLM says it is good; it is accepted as a candidate only if it has evidence, assumptions, a proposed evaluation, and a safety boundary.

## Domain Translation

The paper's default criteria translate as follows:

- Alignment: the idea must directly address the user's research objective.
- Plausibility: the idea must be credible given source evidence, code observations, or benchmark behavior.
- Novelty: the idea should not be a restatement of baseline practice unless it combines existing techniques in a new, testable way.
- Testability: the idea must include a concrete experiment, metric, or benchmark that could falsify or support it.
- Safety: the system must not permit uncontrolled self-modification, unsafe deployment, hidden execution, or claims of measured improvement without evidence.

The target output is a ranked research report, not an autonomous patch. Code changes can be proposed later, but they require explicit local review and verification gates.

## Example Research Objectives

- Find testable ideas that improve an LLM coding agent's repo-level debugging reliability.
- Research methods for reducing hallucinated code edits during multi-file changes.
- Discover prompt, memory, or evaluation strategies that make agentic coding more robust.
- Generate benchmark ideas for measuring whether an LLM actually improves after a workflow change.
- Compare candidate self-improvement loops for cost, reliability, and regressions.

## Example Hypothesis Shape

```json
{
  "title": "Critic-before-edit assumption decomposition",
  "claim": "A critic-before-edit loop that decomposes assumptions before patching will reduce bad multi-file fixes.",
  "rationale": "Many failed code-agent edits come from untested assumptions about call paths and invariants.",
  "assumptions": [
    "The agent can identify assumptions before editing.",
    "Assumption review catches a meaningful fraction of false premises.",
    "Extra review cost does not erase reliability gains."
  ],
  "evidence": [
    "Local bug-fix transcripts showing false premise failures",
    "Research on LLM-as-critic verification",
    "Paper-derived reflection-agent pattern"
  ],
  "test_plan": {
    "experiment": "Run identical bug tasks with and without critic-before-edit.",
    "metrics": ["pass_rate", "regression_count", "tool_calls", "wall_time", "patch_size"],
    "success_condition": "Higher pass rate with no statistically meaningful regression increase."
  },
  "risks": [
    "Critic produces false negatives.",
    "Latency increases too much.",
    "Evaluator preferences overfit to verbose reasoning."
  ]
}
```

## Product Scope

The MVP is a local command-line research engine. It should be deterministic and testable before any real model or web search adapter is added.

In scope:

- A Python package managed with `uv`.
- A CLI command that runs bounded research cycles.
- Structured JSON state for goals, hypotheses, evidence, reviews, matches, Elo ratings, meta-reviews, and reports.
- Deterministic mock model behavior for tests.
- Markdown report generation.
- Safety checks on goals and hypotheses.
- Pairwise tournament ranking with auditable rationale.
- Evolution that creates new hypotheses instead of mutating winners.

Out of scope for the MVP:

- Fully autonomous code rewriting.
- Live deployment or self-modifying agent behavior.
- Claims of actual model improvement without benchmark evidence.
- Unbounded web browsing or unreviewed external tool execution.
- Fine-tuning or reinforcement learning.

## Architecture

### ResearchGoal

Responsibility: capture the user's objective, constraints, preferences, and evaluation criteria.

Fields:

- `id`
- `objective`
- `domain`
- `preferences`
- `constraints`
- `metrics`
- `safety_notes`

### Hypothesis

Responsibility: represent one candidate improvement idea.

Fields:

- `id`
- `title`
- `claim`
- `rationale`
- `assumptions`
- `evidence_refs`
- `test_plan`
- `risks`
- `origin`
- `parent_ids`
- `elo`
- `status`

### EvidenceStore

Responsibility: preserve the information used to generate or judge hypotheses.

Evidence types:

- Paper excerpt
- Local repo observation
- Benchmark result
- User feedback
- External URL or citation
- Generated critique

### GenerationAgent

Responsibility: propose initial hypotheses from a goal and evidence.

MVP behavior:

- Use deterministic templates through a mock model adapter.
- Produce several diverse ideas across prompt design, agent workflow, memory, evaluation, retrieval, and tool use.
- Attach assumptions and test plans to each idea.

### ReflectionAgent

Responsibility: review a hypothesis before it enters the tournament.

Review criteria:

- Alignment
- Plausibility
- Novelty
- Testability
- Safety
- Missing evidence
- Likely failure modes

The reflection output must be structured and include a decision: `accept`, `revise`, or `reject`.

### RankingAgent

Responsibility: compare accepted hypotheses pairwise and update Elo scores.

MVP behavior:

- Choose pairings from accepted hypotheses.
- Compare candidates using structured criteria.
- Emit a match rationale.
- Update ratings from an initial 1200 Elo score.
- Clearly label Elo as an auto-evaluation proxy.

### ProximityAgent

Responsibility: detect near-duplicate ideas and preserve diversity.

MVP behavior:

- Use lexical similarity over titles, claims, and assumptions.
- Store similarity edges.
- Prefer diverse pairings unless a close comparison is useful.

### EvolutionAgent

Responsibility: create new candidate ideas from top-ranked hypotheses and critique patterns.

MVP strategies:

- Feasibility improvement
- Simplification
- Combination of top ideas
- Divergent exploration away from crowded clusters
- Grounding improvement based on missing evidence

The agent must create new hypotheses with `parent_ids`; it must not overwrite originals.

### MetaReviewAgent

Responsibility: synthesize recurring review and tournament patterns into feedback for later cycles.

Outputs:

- Common weaknesses
- Repeated safety concerns
- Missing evidence themes
- Promising research directions
- Prompt feedback for future generation and reflection

### Supervisor

Responsibility: coordinate bounded cycles.

Cycle:

1. Load or create a run state.
2. Parse the research goal.
3. Run safety review on the goal.
4. Generate hypotheses.
5. Reflect and filter hypotheses.
6. Compute proximity.
7. Run ranking matches.
8. Evolve top hypotheses.
9. Run meta-review.
10. Write JSON state and markdown report.

The supervisor must accept limits for cycle count, maximum hypotheses, and maximum matches.

## Data Flow

```text
Research objective
  -> ResearchGoal
  -> goal safety check
  -> EvidenceStore seed
  -> GenerationAgent
  -> Hypotheses
  -> ReflectionAgent
  -> accepted/revised/rejected hypotheses
  -> ProximityAgent
  -> pair scheduling
  -> RankingAgent
  -> Elo leaderboard
  -> EvolutionAgent
  -> new hypotheses
  -> MetaReviewAgent
  -> next-cycle feedback
  -> Markdown research report
```

## CLI

The first CLI should support:

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
```

Expected outputs:

- `runs/demo/state.json`
- `runs/demo/report.md`

## Report Format

The markdown report must include:

- Research objective
- Safety status
- Method summary
- Ranked hypothesis leaderboard
- Top hypothesis details
- Evidence references
- Reviews and recurring critiques
- Evolution lineage
- Recommended next experiments
- Limitations and uncertainty

## Testing Strategy

The MVP should be test-driven around deterministic behavior.

Required tests:

- Research goal parsing creates default criteria.
- Safety review rejects unsafe self-modification goals.
- Generation creates structured hypotheses with test plans.
- Reflection rejects hypotheses missing testability or safety.
- Ranking updates Elo in the expected direction.
- Evolution creates children and preserves parents.
- Meta-review aggregates repeated critique patterns.
- CLI writes valid JSON and markdown report artifacts.

## Safety Model

The system must enforce these invariants:

- No hypothesis can enter ranking unless it passes safety review.
- No generated report may claim measured improvement unless benchmark evidence exists.
- No command may modify source code unless a future explicit implementation mode is added.
- Every run must preserve audit logs.
- Every auto-evaluation score must be labeled as a proxy, not ground truth.

## Implementation Recommendation

Build a small, typed Python package with no runtime service dependency:

- `src/code_scientist/models.py`
- `src/code_scientist/agents.py`
- `src/code_scientist/elo.py`
- `src/code_scientist/supervisor.py`
- `src/code_scientist/reporting.py`
- `src/code_scientist/cli.py`
- `tests/`

Use JSON files for the MVP state. SQLite can be added once the state model stabilizes.

## Success Criteria

The design is implemented when:

- A user can run the CLI with a research objective.
- The system generates, reviews, ranks, evolves, and meta-reviews LLM/code improvement hypotheses.
- The system writes structured state and a readable markdown report.
- Tests verify the core loop deterministically.
- Reports clearly separate generated hypotheses from verified improvements.

