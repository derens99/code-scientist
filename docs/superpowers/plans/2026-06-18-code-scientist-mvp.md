# Code Scientist MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local CLI research engine that generates, reviews, ranks, evolves, and reports testable AI/LLM/code improvement hypotheses based on the AI co-scientist paper.

**Architecture:** The MVP is a deterministic Python package with a bounded supervisor loop, structured dataclass models, paper-derived seed evidence, deterministic agents, Elo ranking, JSON state persistence, and markdown reports. External LLM and search adapters are intentionally deferred until the core loop is testable and auditable.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, standard-library `argparse`, `dataclasses`, `json`, `pathlib`, and `hashlib`.

---

## File Structure

- Create `pyproject.toml`: project metadata, package layout, CLI entry point, pytest configuration.
- Create `README.md`: short usage instructions and safety boundaries.
- Create `src/code_scientist/__init__.py`: package exports.
- Create `src/code_scientist/models.py`: dataclasses for goals, evidence, hypotheses, reviews, matches, meta-reviews, safety decisions, and run state.
- Create `src/code_scientist/paper.py`: curated paper-derived evidence records from `2502.18864.pdf`.
- Create `src/code_scientist/safety.py`: deterministic safety review for goals and hypotheses.
- Create `src/code_scientist/elo.py`: Elo expected-score and update functions.
- Create `src/code_scientist/agents.py`: generation, reflection, proximity, ranking, evolution, and meta-review agents.
- Create `src/code_scientist/supervisor.py`: bounded research-cycle orchestration and JSON persistence.
- Create `src/code_scientist/reporting.py`: markdown report renderer.
- Create `src/code_scientist/cli.py`: `code-scientist run` and `code-scientist report` commands.
- Create `tests/`: deterministic tests for each unit and the end-to-end CLI path.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/code_scientist/__init__.py`
- Create: `tests/test_package.py`

- [ ] **Step 1: Write the failing package import test**

Create `tests/test_package.py`:

```python
from code_scientist import __version__


def test_package_has_version():
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_package.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist'`.

- [ ] **Step 3: Add project metadata**

Create `pyproject.toml`:

```toml
[project]
name = "code-scientist"
version = "0.1.0"
description = "A local research engine for AI, LLM, and coding-agent improvement hypotheses."
requires-python = ">=3.11"
dependencies = []

[project.scripts]
code-scientist = "code_scientist.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `src/code_scientist/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `README.md`:

````markdown
# Code Scientist

Code Scientist is a local research engine inspired by the AI co-scientist paper. It generates, reviews, ranks, evolves, and reports testable hypotheses for improving AI coding agents, LLM workflows, prompts, memory, tool use, and evaluation design.

The MVP is offline and deterministic. It does not autonomously rewrite source code, deploy changes, or claim measured improvement without benchmark evidence.

## Usage

```bash
uv run code-scientist run "Find testable ideas to improve LLM coding agents" --cycles 2 --max-hypotheses 8 --out runs/demo
uv run code-scientist report runs/demo/state.json
```
````

- [ ] **Step 4: Run the package test**

Run:

```bash
uv run pytest tests/test_package.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit scaffolding**

```bash
git add pyproject.toml README.md src/code_scientist/__init__.py tests/test_package.py
git commit -m "chore: scaffold code scientist package"
```

---

### Task 2: Core Data Models

**Files:**
- Create: `src/code_scientist/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing model serialization tests**

Create `tests/test_models.py`:

```python
from code_scientist.models import Evidence, Hypothesis, ResearchGoal, RunState, TestPlan


def test_hypothesis_round_trips_to_dict():
    plan = TestPlan(
        experiment="Run baseline and candidate workflows on seeded bug tasks.",
        metrics=["pass_rate", "regression_count"],
        success_condition="Candidate improves pass rate without more regressions.",
    )
    hypothesis = Hypothesis(
        id="hyp-1",
        title="Critic before edit",
        claim="Assumption critique before editing reduces bad patches.",
        rationale="False assumptions are a common source of bad code edits.",
        assumptions=["The critic can identify false premises."],
        evidence_refs=["ev-1"],
        test_plan=plan,
        risks=["Extra latency"],
        origin="generation",
    )

    data = hypothesis.to_dict()
    restored = Hypothesis.from_dict(data)

    assert restored == hypothesis
    assert restored.elo == 1200.0
    assert restored.status == "candidate"


def test_run_state_round_trips_to_dict():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    evidence = Evidence(
        id="ev-1",
        kind="paper_excerpt",
        source="2502.18864.pdf",
        content="Generate, debate, and evolve hypotheses.",
        notes="Architecture seed",
    )
    state = RunState(goal=goal, evidence=[evidence])

    restored = RunState.from_dict(state.to_dict())

    assert restored.goal.objective == "Improve LLM coding agents"
    assert restored.evidence[0].source == "2502.18864.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.models'`.

- [ ] **Step 3: Implement models**

Create `src/code_scientist/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha1
from typing import Any


def stable_id(prefix: str, text: str) -> str:
    digest = sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


@dataclass(frozen=True)
class ResearchGoal:
    id: str
    objective: str
    domain: str = "ai_llm_code"
    preferences: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_objective(cls, objective: str) -> "ResearchGoal":
        clean = " ".join(objective.split())
        return cls(
            id=stable_id("goal", clean),
            objective=clean,
            preferences=[
                "aligned with the research objective",
                "plausible from code, benchmark, or literature evidence",
                "novel or a novel combination of known techniques",
                "testable with a concrete experiment",
                "safe and auditable",
            ],
            constraints=[
                "do not autonomously modify source code",
                "do not claim measured improvement without benchmark evidence",
            ],
            metrics=["pass_rate", "regression_count", "tool_calls", "wall_time", "cost"],
            safety_notes=["human review required before applying code changes"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchGoal":
        return cls(**data)


@dataclass(frozen=True)
class TestPlan:
    experiment: str
    metrics: list[str]
    success_condition: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestPlan":
        return cls(**data)


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    source: str
    content: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        return cls(**data)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    title: str
    claim: str
    rationale: str
    assumptions: list[str]
    evidence_refs: list[str]
    test_plan: TestPlan
    risks: list[str]
    origin: str
    parent_ids: list[str] = field(default_factory=list)
    elo: float = 1200.0
    status: str = "candidate"

    def with_status(self, status: str) -> "Hypothesis":
        return Hypothesis(**{**self.to_dict(), "status": status})

    def with_elo(self, elo: float) -> "Hypothesis":
        return Hypothesis(**{**self.to_dict(), "elo": elo})

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["test_plan"] = self.test_plan.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        copied = dict(data)
        copied["test_plan"] = TestPlan.from_dict(copied["test_plan"])
        return cls(**copied)


@dataclass(frozen=True)
class Review:
    id: str
    hypothesis_id: str
    decision: str
    scores: dict[str, int]
    strengths: list[str]
    weaknesses: list[str]
    safety_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Review":
        return cls(**data)


@dataclass(frozen=True)
class Match:
    id: str
    hypothesis_a: str
    hypothesis_b: str
    winner: str
    rationale: str
    elo_before: dict[str, float]
    elo_after: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Match":
        return cls(**data)


@dataclass(frozen=True)
class MetaReview:
    id: str
    common_weaknesses: list[str]
    safety_concerns: list[str]
    missing_evidence: list[str]
    promising_directions: list[str]
    prompt_feedback: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetaReview":
        return cls(**data)


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SafetyDecision":
        return cls(**data)


@dataclass(frozen=True)
class RunState:
    goal: ResearchGoal
    evidence: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    meta_reviews: list[MetaReview] = field(default_factory=list)
    safety: SafetyDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "reviews": [item.to_dict() for item in self.reviews],
            "matches": [item.to_dict() for item in self.matches],
            "meta_reviews": [item.to_dict() for item in self.meta_reviews],
            "safety": self.safety.to_dict() if self.safety else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        safety_data = data.get("safety")
        return cls(
            goal=ResearchGoal.from_dict(data["goal"]),
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            hypotheses=[Hypothesis.from_dict(item) for item in data.get("hypotheses", [])],
            reviews=[Review.from_dict(item) for item in data.get("reviews", [])],
            matches=[Match.from_dict(item) for item in data.get("matches", [])],
            meta_reviews=[MetaReview.from_dict(item) for item in data.get("meta_reviews", [])],
            safety=SafetyDecision.from_dict(safety_data) if safety_data else None,
        )
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit models**

```bash
git add src/code_scientist/models.py tests/test_models.py
git commit -m "feat: add research state models"
```

---

### Task 3: Paper-Derived Evidence

**Files:**
- Create: `src/code_scientist/paper.py`
- Create: `tests/test_paper.py`

- [ ] **Step 1: Write failing paper evidence tests**

Create `tests/test_paper.py`:

```python
from code_scientist.paper import seed_paper_evidence


def test_seed_paper_evidence_contains_core_loop():
    evidence = seed_paper_evidence()
    contents = " ".join(item.content for item in evidence)

    assert len(evidence) >= 5
    assert "generate, debate, and evolve" in contents
    assert "Elo" in contents
    assert "safety" in contents.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_paper.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.paper'`.

- [ ] **Step 3: Implement paper evidence**

Create `src/code_scientist/paper.py`:

```python
from __future__ import annotations

from code_scientist.models import Evidence, stable_id


def _evidence(kind: str, content: str, notes: str) -> Evidence:
    return Evidence(
        id=stable_id("ev", content),
        kind=kind,
        source="2502.18864.pdf",
        content=content,
        notes=notes,
    )


def seed_paper_evidence() -> list[Evidence]:
    return [
        _evidence(
            "paper_architecture",
            "The AI co-scientist uses a generate, debate, and evolve approach to hypothesis generation.",
            "Core loop to translate into AI/LLM improvement research.",
        ),
        _evidence(
            "paper_architecture",
            "A supervisor coordinates specialized generation, reflection, ranking, proximity, evolution, and meta-review agents.",
            "Agent decomposition for the Code Scientist MVP.",
        ),
        _evidence(
            "paper_evaluation",
            "The ranking agent uses an Elo-based tournament to prioritize hypotheses, while noting that Elo is an auto-evaluation proxy.",
            "Ranking should be auditable and labeled as proxy evaluation.",
        ),
        _evidence(
            "paper_feedback_loop",
            "Meta-review synthesizes recurring critique patterns and appends feedback to future agent prompts without model retraining.",
            "Self-improvement should start as externalized prompt and process feedback.",
        ),
        _evidence(
            "paper_safety",
            "The system reviews research goals and generated hypotheses for safety and keeps comprehensive logs for auditability.",
            "Safety gates are required before ranking and reporting ideas.",
        ),
        _evidence(
            "paper_limitations",
            "The paper warns that literature search can miss prior work, LLMs can hallucinate, and auto-evaluation metrics need broader validation.",
            "Reports must separate generated hypotheses from verified improvements.",
        ),
    ]
```

- [ ] **Step 4: Run paper tests**

Run:

```bash
uv run pytest tests/test_paper.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit paper evidence**

```bash
git add src/code_scientist/paper.py tests/test_paper.py
git commit -m "feat: seed paper-derived evidence"
```

---

### Task 4: Safety and Elo Utilities

**Files:**
- Create: `src/code_scientist/safety.py`
- Create: `src/code_scientist/elo.py`
- Create: `tests/test_safety_elo.py`

- [ ] **Step 1: Write failing safety and Elo tests**

Create `tests/test_safety_elo.py`:

```python
from code_scientist.elo import update_elo
from code_scientist.models import Hypothesis, TestPlan
from code_scientist.safety import review_goal_safety, review_hypothesis_safety


def _hypothesis(claim: str) -> Hypothesis:
    return Hypothesis(
        id="hyp-x",
        title="Example",
        claim=claim,
        rationale="A concrete rationale.",
        assumptions=["A testable assumption."],
        evidence_refs=["ev-1"],
        test_plan=TestPlan(
            experiment="Compare baseline and candidate.",
            metrics=["pass_rate"],
            success_condition="Candidate improves pass rate.",
        ),
        risks=["Possible cost increase"],
        origin="test",
    )


def test_goal_safety_blocks_uncontrolled_self_modification():
    decision = review_goal_safety("Let the model secretly rewrite and deploy itself")

    assert decision.allowed is False
    assert "self-modification" in decision.flags


def test_hypothesis_safety_requires_audit_boundary():
    decision = review_hypothesis_safety(_hypothesis("Autonomously deploy patches without review"))

    assert decision.allowed is False
    assert "unreviewed-deployment" in decision.flags


def test_update_elo_moves_winner_up_and_loser_down():
    winner, loser = update_elo(1200.0, 1200.0)

    assert winner > 1200.0
    assert loser < 1200.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_safety_elo.py -v
```

Expected: FAIL with missing `code_scientist.elo` and `code_scientist.safety`.

- [ ] **Step 3: Implement Elo**

Create `src/code_scientist/elo.py`:

```python
from __future__ import annotations


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(winner_rating: float, loser_rating: float, k_factor: float = 32.0) -> tuple[float, float]:
    winner_expected = expected_score(winner_rating, loser_rating)
    loser_expected = expected_score(loser_rating, winner_rating)
    return (
        winner_rating + k_factor * (1.0 - winner_expected),
        loser_rating + k_factor * (0.0 - loser_expected),
    )
```

- [ ] **Step 4: Implement safety review**

Create `src/code_scientist/safety.py`:

```python
from __future__ import annotations

from code_scientist.models import Hypothesis, SafetyDecision


SELF_MODIFICATION_TERMS = ("rewrite itself", "modify itself", "self-modify", "self modification")
SECRET_TERMS = ("secretly", "hide", "without logging", "covert")
DEPLOY_TERMS = ("deploy", "production", "release")
NO_REVIEW_TERMS = ("without review", "without human", "unreviewed")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def review_goal_safety(objective: str) -> SafetyDecision:
    flags: list[str] = []
    if _contains_any(objective, SELF_MODIFICATION_TERMS):
        flags.append("self-modification")
    if _contains_any(objective, SECRET_TERMS):
        flags.append("hidden-execution")
    if _contains_any(objective, DEPLOY_TERMS) and _contains_any(objective, NO_REVIEW_TERMS):
        flags.append("unreviewed-deployment")
    if flags:
        return SafetyDecision(False, "Objective requests unsafe autonomous behavior.", flags)
    return SafetyDecision(True, "Objective is allowed for local research planning.", [])


def review_hypothesis_safety(hypothesis: Hypothesis) -> SafetyDecision:
    text = " ".join([hypothesis.title, hypothesis.claim, hypothesis.rationale, *hypothesis.risks])
    flags: list[str] = []
    if _contains_any(text, SELF_MODIFICATION_TERMS):
        flags.append("self-modification")
    if _contains_any(text, DEPLOY_TERMS) and _contains_any(text, NO_REVIEW_TERMS):
        flags.append("unreviewed-deployment")
    if _contains_any(text, SECRET_TERMS):
        flags.append("hidden-execution")
    if flags:
        return SafetyDecision(False, "Hypothesis violates local research safety boundaries.", flags)
    return SafetyDecision(True, "Hypothesis stays within local research boundaries.", [])
```

- [ ] **Step 5: Run safety and Elo tests**

Run:

```bash
uv run pytest tests/test_safety_elo.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit utilities**

```bash
git add src/code_scientist/safety.py src/code_scientist/elo.py tests/test_safety_elo.py
git commit -m "feat: add safety and elo utilities"
```

---

### Task 5: Deterministic Agents

**Files:**
- Create: `src/code_scientist/agents.py`
- Create: `tests/test_agents.py`

- [ ] **Step 1: Write failing agent tests**

Create `tests/test_agents.py`:

```python
from code_scientist.agents import (
    EvolutionAgent,
    GenerationAgent,
    MetaReviewAgent,
    ProximityAgent,
    RankingAgent,
    ReflectionAgent,
)
from code_scientist.models import ResearchGoal
from code_scientist.paper import seed_paper_evidence


def test_generation_creates_structured_hypotheses():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=3)

    assert len(hypotheses) == 3
    assert all(item.test_plan.experiment for item in hypotheses)
    assert all(item.assumptions for item in hypotheses)


def test_reflection_accepts_testable_safe_hypothesis():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypothesis = GenerationAgent().generate(goal, seed_paper_evidence(), limit=1)[0]
    review = ReflectionAgent().review(goal, hypothesis)

    assert review.decision == "accept"
    assert review.scores["testability"] >= 4


def test_ranking_updates_leaderboard_with_match():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=2)
    ranked, match = RankingAgent().compare(goal, hypotheses[0], hypotheses[1])

    assert match.winner in {hypotheses[0].id, hypotheses[1].id}
    assert len(ranked) == 2
    assert ranked[0].elo != ranked[1].elo


def test_proximity_finds_similarity_edges():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=3)
    edges = ProximityAgent().compute(hypotheses)

    assert edges
    assert all(0.0 <= item["similarity"] <= 1.0 for item in edges)


def test_evolution_creates_child_without_replacing_parent():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    parent = GenerationAgent().generate(goal, seed_paper_evidence(), limit=1)[0]
    child = EvolutionAgent().evolve(goal, [parent], feedback=["Make experiments cheaper."])[0]

    assert child.id != parent.id
    assert child.parent_ids == [parent.id]
    assert parent.title in child.rationale


def test_meta_review_aggregates_weaknesses():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=2)
    reviews = [ReflectionAgent().review(goal, item) for item in hypotheses]
    meta = MetaReviewAgent().summarize(goal, reviews, [])

    assert meta.common_weaknesses
    assert meta.prompt_feedback
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_agents.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.agents'`.

- [ ] **Step 3: Implement deterministic agents**

Create `src/code_scientist/agents.py`:

```python
from __future__ import annotations

from collections import Counter
from itertools import combinations

from code_scientist.elo import update_elo
from code_scientist.models import Hypothesis, Match, MetaReview, ResearchGoal, Review, TestPlan, stable_id
from code_scientist.safety import review_hypothesis_safety


class GenerationAgent:
    def generate(self, goal: ResearchGoal, evidence: list[object], limit: int = 6) -> list[Hypothesis]:
        evidence_refs = [getattr(item, "id", "") for item in evidence][:3]
        blueprints = [
            (
                "Critic-before-edit assumption decomposition",
                "A critic-before-edit loop that decomposes assumptions before patching will reduce bad repo-level fixes.",
                "False premises about call paths, invariants, and test scope are common causes of bad edits.",
                ["The agent can state assumptions before editing.", "A critic can catch false premises cheaply."],
                ["critic false negatives", "extra latency"],
            ),
            (
                "Tournament-ranked prompt variants",
                "Pairwise tournament ranking of prompt variants will identify more reliable coding-agent workflows than single-prompt selection.",
                "The paper's Elo tournament can be adapted to compare prompt and workflow hypotheses.",
                ["Prompt variants can be evaluated on comparable tasks.", "Pairwise judging is less noisy than absolute scoring."],
                ["judge bias", "overfitting to benchmark tasks"],
            ),
            (
                "Failure-derived benchmark seeds",
                "Mining prior failed agent traces into benchmark seeds will improve measurement of future workflow changes.",
                "Regression-focused evals need examples that reflect real observed failure modes.",
                ["Failure traces are available.", "Failures can be minimized into reproducible tasks."],
                ["private data leakage", "narrow benchmark coverage"],
            ),
            (
                "Memory with explicit contradiction checks",
                "Agent memory that records contradictions and stale facts will reduce repeated reasoning errors.",
                "Long-horizon agent work fails when memory is accepted without freshness checks.",
                ["Memory entries can be classified by freshness.", "Contradictions can be surfaced before planning."],
                ["memory bloat", "false contradiction alerts"],
            ),
            (
                "Tool-use budget scheduler",
                "A scheduler that allocates tool calls by uncertainty and expected information gain will reduce cost without lowering pass rate.",
                "The paper allocates compute based on tournament state; coding agents can allocate shell and search effort similarly.",
                ["Uncertainty can be estimated from reviews.", "Tool calls have measurable cost and value."],
                ["under-exploration", "bad uncertainty estimates"],
            ),
            (
                "Meta-review prompt feedback",
                "Summarizing recurring review critiques into prompt feedback will improve later generations without model training.",
                "The paper's meta-review loop enables process improvement through externalized feedback.",
                ["Recurring critique patterns are stable enough to reuse.", "Prompt feedback changes later hypotheses."],
                ["feedback overfitting", "generic critiques"],
            ),
        ]
        hypotheses: list[Hypothesis] = []
        for title, claim, rationale, assumptions, risks in blueprints[:limit]:
            identity = f"{goal.id}:{title}:{claim}"
            hypotheses.append(
                Hypothesis(
                    id=stable_id("hyp", identity),
                    title=title,
                    claim=claim,
                    rationale=rationale,
                    assumptions=assumptions,
                    evidence_refs=evidence_refs,
                    test_plan=TestPlan(
                        experiment=f"Compare baseline coding-agent workflow against: {title}.",
                        metrics=goal.metrics,
                        success_condition="Candidate improves pass rate or regression count without unacceptable cost increase.",
                    ),
                    risks=risks,
                    origin="generation",
                )
            )
        return hypotheses


class ReflectionAgent:
    def review(self, goal: ResearchGoal, hypothesis: Hypothesis) -> Review:
        safety = review_hypothesis_safety(hypothesis)
        has_test = bool(hypothesis.test_plan.experiment and hypothesis.test_plan.metrics)
        has_evidence = bool(hypothesis.evidence_refs)
        scores = {
            "alignment": 5 if "agent" in hypothesis.claim.lower() or "llm" in hypothesis.claim.lower() else 3,
            "plausibility": 4 if hypothesis.assumptions else 2,
            "novelty": 4,
            "testability": 5 if has_test else 1,
            "safety": 5 if safety.allowed else 1,
        }
        weaknesses: list[str] = []
        if not has_evidence:
            weaknesses.append("missing evidence references")
        if not has_test:
            weaknesses.append("missing concrete test plan")
        if not safety.allowed:
            weaknesses.extend(safety.flags)
        if not weaknesses:
            weaknesses.append("needs measured benchmark evidence before claiming improvement")
        decision = "accept" if safety.allowed and has_test else "reject"
        return Review(
            id=stable_id("rev", f"{goal.id}:{hypothesis.id}:{decision}"),
            hypothesis_id=hypothesis.id,
            decision=decision,
            scores=scores,
            strengths=["structured hypothesis", "explicit assumptions", "concrete evaluation path"],
            weaknesses=weaknesses,
            safety_notes=[safety.reason],
        )


class ProximityAgent:
    def compute(self, hypotheses: list[Hypothesis]) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        for left, right in combinations(hypotheses, 2):
            left_tokens = set(_tokens(left.title + " " + left.claim))
            right_tokens = set(_tokens(right.title + " " + right.claim))
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
            edges.append({"source": left.id, "target": right.id, "similarity": round(similarity, 3)})
        return edges


class RankingAgent:
    def compare(self, goal: ResearchGoal, first: Hypothesis, second: Hypothesis) -> tuple[list[Hypothesis], Match]:
        first_score = _rank_score(first)
        second_score = _rank_score(second)
        winner, loser = (first, second) if first_score >= second_score else (second, first)
        winner_elo, loser_elo = update_elo(winner.elo, loser.elo)
        updated = {
            winner.id: winner.with_elo(winner_elo),
            loser.id: loser.with_elo(loser_elo),
        }
        ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
        match = Match(
            id=stable_id("match", f"{goal.id}:{first.id}:{second.id}"),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner.id,
            rationale=f"Selected {winner.title} because it has stronger structured evidence, assumptions, and testability.",
            elo_before={first.id: first.elo, second.id: second.elo},
            elo_after={item.id: item.elo for item in ranked},
        )
        return ranked, match


class EvolutionAgent:
    def evolve(self, goal: ResearchGoal, parents: list[Hypothesis], feedback: list[str], limit: int = 2) -> list[Hypothesis]:
        children: list[Hypothesis] = []
        for parent in parents[:limit]:
            feedback_text = "; ".join(feedback) if feedback else "tighten evidence and reduce evaluation cost"
            title = f"Simplified {parent.title}"
            claim = f"{parent.claim} A simplified variant should reduce cost and make evaluation easier."
            child = Hypothesis(
                id=stable_id("hyp", f"{goal.id}:{parent.id}:simplified:{feedback_text}"),
                title=title,
                claim=claim,
                rationale=f"Derived from {parent.title}; meta-review feedback: {feedback_text}.",
                assumptions=[*parent.assumptions, "The simplified variant preserves the core mechanism."],
                evidence_refs=parent.evidence_refs,
                test_plan=TestPlan(
                    experiment=f"Compare baseline, parent idea, and simplified variant for: {parent.title}.",
                    metrics=parent.test_plan.metrics,
                    success_condition="Simplified variant keeps reliability gains while reducing cost or complexity.",
                ),
                risks=[*parent.risks, "simplification may remove the useful mechanism"],
                origin="evolution",
                parent_ids=[parent.id],
            )
            children.append(child)
        return children


class MetaReviewAgent:
    def summarize(self, goal: ResearchGoal, reviews: list[Review], matches: list[Match]) -> MetaReview:
        weakness_counts = Counter(weakness for review in reviews for weakness in review.weaknesses)
        safety_counts = Counter(note for review in reviews for note in review.safety_notes)
        common_weaknesses = [item for item, _count in weakness_counts.most_common(5)]
        if not common_weaknesses:
            common_weaknesses = ["needs measured benchmark evidence before claiming improvement"]
        prompt_feedback = [
            "Require every hypothesis to name an experiment and metric.",
            "Prefer ideas with explicit assumptions and audit boundaries.",
            "Label Elo as proxy auto-evaluation rather than ground truth.",
        ]
        return MetaReview(
            id=stable_id("meta", f"{goal.id}:{len(reviews)}:{len(matches)}"),
            common_weaknesses=common_weaknesses,
            safety_concerns=[item for item, _count in safety_counts.most_common(3)],
            missing_evidence=["benchmark deltas", "repo-specific failure examples"],
            promising_directions=["critic loops", "evaluation design", "memory freshness", "tool-use scheduling"],
            prompt_feedback=prompt_feedback,
        )


def _tokens(text: str) -> list[str]:
    return [token.strip(".,:;()[]{}").lower() for token in text.split() if len(token.strip(".,:;()[]{}")) > 2]


def _rank_score(hypothesis: Hypothesis) -> int:
    return (
        len(hypothesis.assumptions)
        + len(hypothesis.evidence_refs)
        + len(hypothesis.test_plan.metrics)
        - len([risk for risk in hypothesis.risks if "unsafe" in risk.lower()])
    )
```

- [ ] **Step 4: Run agent tests**

Run:

```bash
uv run pytest tests/test_agents.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit agents**

```bash
git add src/code_scientist/agents.py tests/test_agents.py
git commit -m "feat: add deterministic research agents"
```

---

### Task 6: Supervisor and Persistence

**Files:**
- Create: `src/code_scientist/supervisor.py`
- Create: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing supervisor tests**

Create `tests/test_supervisor.py`:

```python
import json

from code_scientist.models import RunState
from code_scientist.supervisor import run_research_cycle


def test_supervisor_writes_state(tmp_path):
    out_dir = tmp_path / "run"
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=2,
        out_dir=out_dir,
    )

    state_path = out_dir / "state.json"
    assert state_path.exists()
    restored = RunState.from_dict(json.loads(state_path.read_text()))
    assert restored.goal.objective == state.goal.objective
    assert restored.hypotheses
    assert restored.reviews
    assert restored.matches
    assert restored.meta_reviews
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_supervisor.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.supervisor'`.

- [ ] **Step 3: Implement supervisor**

Create `src/code_scientist/supervisor.py`:

```python
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from code_scientist.agents import (
    EvolutionAgent,
    GenerationAgent,
    MetaReviewAgent,
    ProximityAgent,
    RankingAgent,
    ReflectionAgent,
)
from code_scientist.models import Hypothesis, ResearchGoal, RunState
from code_scientist.paper import seed_paper_evidence
from code_scientist.safety import review_goal_safety


def run_research_cycle(
    objective: str,
    cycles: int,
    max_hypotheses: int,
    max_matches: int,
    out_dir: str | Path,
) -> RunState:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    goal = ResearchGoal.from_objective(objective)
    safety = review_goal_safety(goal.objective)
    state = RunState(goal=goal, evidence=seed_paper_evidence(), safety=safety)
    if not safety.allowed:
        _write_state(out_path / "state.json", state)
        return state

    generation = GenerationAgent()
    reflection = ReflectionAgent()
    proximity = ProximityAgent()
    ranking = RankingAgent()
    evolution = EvolutionAgent()
    meta_review = MetaReviewAgent()

    hypotheses: list[Hypothesis] = []
    reviews = []
    matches = []
    metas = []
    feedback: list[str] = []

    for _cycle in range(cycles):
        remaining = max(max_hypotheses - len(hypotheses), 0)
        generated = generation.generate(goal, state.evidence, limit=remaining)
        reviewed = [reflection.review(goal, item) for item in generated]
        accepted_ids = {review.hypothesis_id for review in reviewed if review.decision == "accept"}
        accepted = [item.with_status("accepted") for item in generated if item.id in accepted_ids]
        hypotheses.extend(accepted)
        reviews.extend(reviewed)

        proximity.compute(hypotheses)
        for first, second in list(combinations(hypotheses, 2))[:max_matches]:
            ranked_pair, match = ranking.compare(goal, first, second)
            hypotheses = _replace_hypotheses(hypotheses, ranked_pair)
            matches.append(match)

        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:2]
        children = evolution.evolve(goal, leaders, feedback, limit=max(1, min(2, max_hypotheses - len(hypotheses))))
        child_reviews = [reflection.review(goal, item) for item in children]
        accepted_child_ids = {review.hypothesis_id for review in child_reviews if review.decision == "accept"}
        hypotheses.extend([item.with_status("accepted") for item in children if item.id in accepted_child_ids])
        reviews.extend(child_reviews)

        meta = meta_review.summarize(goal, reviews, matches)
        metas.append(meta)
        feedback = meta.prompt_feedback

    state = RunState(
        goal=goal,
        evidence=state.evidence,
        hypotheses=sorted(hypotheses, key=lambda item: item.elo, reverse=True),
        reviews=reviews,
        matches=matches,
        meta_reviews=metas,
        safety=safety,
    )
    _write_state(out_path / "state.json", state)
    return state


def load_state(path: str | Path) -> RunState:
    return RunState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_state(path: Path, state: RunState) -> None:
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _replace_hypotheses(existing: list[Hypothesis], replacements: list[Hypothesis]) -> list[Hypothesis]:
    by_id = {item.id: item for item in existing}
    for item in replacements:
        by_id[item.id] = item
    return list(by_id.values())
```

- [ ] **Step 4: Run supervisor tests**

Run:

```bash
uv run pytest tests/test_supervisor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit supervisor**

```bash
git add src/code_scientist/supervisor.py tests/test_supervisor.py
git commit -m "feat: add research supervisor"
```

---

### Task 7: Markdown Reporting

**Files:**
- Create: `src/code_scientist/reporting.py`
- Create: `tests/test_reporting.py`

- [ ] **Step 1: Write failing report tests**

Create `tests/test_reporting.py`:

```python
from code_scientist.reporting import render_report
from code_scientist.supervisor import run_research_cycle


def test_render_report_includes_leaderboard_and_limitations(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=2,
        out_dir=tmp_path / "run",
    )

    report = render_report(state)

    assert "# Code Scientist Research Report" in report
    assert "Ranked Hypotheses" in report
    assert "Elo is an auto-evaluation proxy" in report
    assert "Recommended Next Experiments" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_reporting.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.reporting'`.

- [ ] **Step 3: Implement report renderer**

Create `src/code_scientist/reporting.py`:

```python
from __future__ import annotations

from code_scientist.models import RunState


def render_report(state: RunState) -> str:
    lines: list[str] = [
        "# Code Scientist Research Report",
        "",
        f"Objective: {state.goal.objective}",
        "",
        "## Safety Status",
        "",
        f"- Allowed: {state.safety.allowed if state.safety else True}",
        f"- Reason: {state.safety.reason if state.safety else 'No safety decision recorded.'}",
        "",
        "## Method Summary",
        "",
        "This run generated, reviewed, ranked, evolved, and meta-reviewed AI/LLM/code improvement hypotheses.",
        "Elo is an auto-evaluation proxy, not ground truth.",
        "",
        "## Ranked Hypotheses",
        "",
    ]
    for index, hypothesis in enumerate(state.hypotheses, start=1):
        lines.extend(
            [
                f"{index}. {hypothesis.title} - Elo {hypothesis.elo:.1f}",
                f"   - Claim: {hypothesis.claim}",
                f"   - Test: {hypothesis.test_plan.experiment}",
                f"   - Metrics: {', '.join(hypothesis.test_plan.metrics)}",
            ]
        )

    lines.extend(["", "## Reviews And Critiques", ""])
    for review in state.reviews:
        lines.append(f"- {review.hypothesis_id}: {review.decision}; weaknesses: {', '.join(review.weaknesses)}")

    lines.extend(["", "## Evolution Lineage", ""])
    children = [item for item in state.hypotheses if item.parent_ids]
    if children:
        for child in children:
            lines.append(f"- {child.id} derives from {', '.join(child.parent_ids)}")
    else:
        lines.append("- No evolved hypotheses were accepted in this run.")

    lines.extend(["", "## Meta-Review", ""])
    for meta in state.meta_reviews:
        lines.append(f"- Common weaknesses: {', '.join(meta.common_weaknesses)}")
        lines.append(f"- Prompt feedback: {', '.join(meta.prompt_feedback)}")

    lines.extend(["", "## Recommended Next Experiments", ""])
    for hypothesis in state.hypotheses[:3]:
        lines.append(f"- Test `{hypothesis.title}` with metrics: {', '.join(hypothesis.test_plan.metrics)}")

    lines.extend(
        [
            "",
            "## Limitations And Uncertainty",
            "",
            "- Generated hypotheses are research candidates, not verified improvements.",
            "- Elo rankings are internal preference signals and require benchmark validation.",
            "- Reports must not be used as evidence of model improvement without measured deltas.",
            "",
        ]
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run reporting tests**

Run:

```bash
uv run pytest tests/test_reporting.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit reporting**

```bash
git add src/code_scientist/reporting.py tests/test_reporting.py
git commit -m "feat: render research reports"
```

---

### Task 8: CLI Commands

**Files:**
- Create: `src/code_scientist/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import json

from code_scientist.cli import main


def test_cli_run_writes_state_and_report(tmp_path):
    out_dir = tmp_path / "demo"
    exit_code = main(
        [
            "run",
            "Find testable ideas to improve LLM coding agents",
            "--cycles",
            "1",
            "--max-hypotheses",
            "4",
            "--max-matches",
            "2",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "state.json").exists()
    assert (out_dir / "report.md").exists()
    data = json.loads((out_dir / "state.json").read_text())
    assert data["hypotheses"]


def test_cli_report_renders_existing_state(tmp_path, capsys):
    out_dir = tmp_path / "demo"
    main(["run", "Improve LLM coding agents", "--out", str(out_dir)])
    exit_code = main(["report", str(out_dir / "state.json")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Code Scientist Research Report" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'code_scientist.cli'`.

- [ ] **Step 3: Implement CLI**

Create `src/code_scientist/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from code_scientist.reporting import render_report
from code_scientist.supervisor import load_state, run_research_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-scientist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bounded research cycle.")
    run_parser.add_argument("objective")
    run_parser.add_argument("--cycles", type=int, default=1)
    run_parser.add_argument("--max-hypotheses", type=int, default=6)
    run_parser.add_argument("--max-matches", type=int, default=4)
    run_parser.add_argument("--out", default="runs/demo")

    report_parser = subparsers.add_parser("report", help="Render a report from state JSON.")
    report_parser.add_argument("state_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        out_dir = Path(args.out)
        state = run_research_cycle(
            objective=args.objective,
            cycles=args.cycles,
            max_hypotheses=args.max_hypotheses,
            max_matches=args.max_matches,
            out_dir=out_dir,
        )
        report = render_report(state)
        (out_dir / "report.md").write_text(report, encoding="utf-8")
        print(f"Wrote {out_dir / 'state.json'}")
        print(f"Wrote {out_dir / 'report.md'}")
        return 0
    if args.command == "report":
        report = render_report(load_state(args.state_json))
        print(report)
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit CLI**

```bash
git add src/code_scientist/cli.py tests/test_cli.py
git commit -m "feat: add code scientist cli"
```

---

### Task 9: End-to-End Verification And Documentation Polish

**Files:**
- Modify: `README.md`
- Generated during verification: `runs/demo/state.json`
- Generated during verification: `runs/demo/report.md`

- [ ] **Step 1: Run the actual MVP command**

Run:

```bash
uv run code-scientist run "Find testable ideas that could improve LLM coding agents" --cycles 2 --max-hypotheses 8 --max-matches 4 --out runs/demo
```

Expected:

```text
Wrote runs/demo/state.json
Wrote runs/demo/report.md
```

- [ ] **Step 2: Inspect generated report**

Run:

```bash
sed -n '1,220p' runs/demo/report.md
```

Expected: report includes the objective, safety status, ranked hypotheses, review critiques, evolution lineage, meta-review, recommended next experiments, and limitations.

- [ ] **Step 3: Update README with verified command output**

Modify `README.md` to include:

````markdown
## Verified Local Demo

The MVP can be verified with:

```bash
uv run code-scientist run "Find testable ideas that could improve LLM coding agents" --cycles 2 --max-hypotheses 8 --max-matches 4 --out runs/demo
uv run code-scientist report runs/demo/state.json
```

The generated report separates hypotheses from verified improvements and labels Elo as an auto-evaluation proxy.
````

- [ ] **Step 4: Run all tests**

Run:

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit documentation polish**

```bash
git add README.md
git commit -m "docs: add verified demo instructions"
```

---

## Self-Review Checklist

- Spec coverage: Tasks cover the package, paper-derived evidence, models, safety, Elo, agents, supervisor, reporting, CLI, tests, and demo artifacts required by the design.
- Type consistency: `ResearchGoal`, `Hypothesis`, `Evidence`, `Review`, `Match`, `MetaReview`, `SafetyDecision`, and `RunState` are introduced before use by other tasks.
- Verification: Each feature task starts with a failing test, then implementation, then a passing test command.
- Safety: Goal and hypothesis safety gates exist before ranking and reporting.
- Scope: The MVP researches and reports ideas; autonomous source-code modification is excluded.
