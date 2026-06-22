from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha1
from typing import Any, ClassVar


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
    def from_objective(cls, objective: str) -> ResearchGoal:
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
    def from_dict(cls, data: dict[str, Any]) -> ResearchGoal:
        return cls(**data)


@dataclass(frozen=True)
class ResearchPlanConfig:
    id: str
    goal_id: str
    proposal_preferences: list[str]
    evaluation_criteria: list[str]
    generation_methods: list[str]
    review_types: list[str]
    evolution_strategies: list[str]
    scheduler_weights: dict[str, float]
    constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_goal(cls, goal: ResearchGoal) -> ResearchPlanConfig:
        identity = f"{goal.id}:{goal.objective}:{','.join(goal.metrics)}"
        return cls(
            id=stable_id("plan", identity),
            goal_id=goal.id,
            proposal_preferences=[*goal.preferences],
            evaluation_criteria=[
                "alignment",
                "plausibility",
                "novelty",
                "testability",
                "safety",
                *goal.metrics,
            ],
            generation_methods=[
                "paper_seeded_idea_generation",
                "assumption_decomposition",
                "research_expansion_from_meta_review",
            ],
            review_types=[
                "initial_review",
                "safety_review",
                "recurrent_tournament_review",
            ],
            evolution_strategies=[
                "simplification",
                "feasibility_improvement",
                "feedback_grounding",
            ],
            scheduler_weights={
                "generation": 1.0,
                "reflection": 1.0,
                "proximity": 0.5,
                "ranking": 1.0,
                "evolution": 0.75,
                "meta_review": 0.5,
            },
            constraints=[*goal.constraints],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchPlanConfig:
        return cls(**data)


@dataclass(frozen=True)
class TestPlan:
    __test__: ClassVar[bool] = False

    experiment: str
    metrics: list[str]
    success_condition: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestPlan:
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
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
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

    def with_status(self, status: str) -> Hypothesis:
        return replace(self, status=status)

    def with_elo(self, elo: float) -> Hypothesis:
        return replace(self, elo=elo)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["test_plan"] = self.test_plan.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hypothesis:
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
    def from_dict(cls, data: dict[str, Any]) -> Review:
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
    def from_dict(cls, data: dict[str, Any]) -> Match:
        return cls(**data)


@dataclass(frozen=True)
class ProximityEdge:
    source: str
    target: str
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProximityEdge:
        return cls(**data)


@dataclass(frozen=True)
class BenchmarkResult:
    id: str
    name: str
    source: str
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]
    success: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkResult:
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
    def from_dict(cls, data: dict[str, Any]) -> MetaReview:
        return cls(**data)


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SafetyDecision:
        return cls(**data)


@dataclass(frozen=True)
class ContextSnapshot:
    id: str
    cycle: int
    generated_total: int
    accepted_total: int
    review_total: int
    match_total: int
    meta_review_total: int
    top_hypothesis_ids: list[str]
    origin_counts: dict[str, int]
    status_counts: dict[str, int]
    proximity_edge_count: int
    scheduler_weights: dict[str, float]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextSnapshot:
        return cls(**data)


@dataclass(frozen=True)
class RunState:
    goal: ResearchGoal
    plan: ResearchPlanConfig | None = None
    evidence: list[Evidence] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    proximity_edges: list[ProximityEdge] = field(default_factory=list)
    benchmark_results: list[BenchmarkResult] = field(default_factory=list)
    meta_reviews: list[MetaReview] = field(default_factory=list)
    context_snapshots: list[ContextSnapshot] = field(default_factory=list)
    safety: SafetyDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "plan": self.plan.to_dict() if self.plan else None,
            "evidence": [item.to_dict() for item in self.evidence],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "reviews": [item.to_dict() for item in self.reviews],
            "matches": [item.to_dict() for item in self.matches],
            "proximity_edges": [item.to_dict() for item in self.proximity_edges],
            "benchmark_results": [item.to_dict() for item in self.benchmark_results],
            "meta_reviews": [item.to_dict() for item in self.meta_reviews],
            "context_snapshots": [item.to_dict() for item in self.context_snapshots],
            "safety": self.safety.to_dict() if self.safety else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        safety_data = data.get("safety")
        plan_data = data.get("plan")
        return cls(
            goal=ResearchGoal.from_dict(data["goal"]),
            plan=ResearchPlanConfig.from_dict(plan_data) if plan_data else None,
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            hypotheses=[Hypothesis.from_dict(item) for item in data.get("hypotheses", [])],
            reviews=[Review.from_dict(item) for item in data.get("reviews", [])],
            matches=[Match.from_dict(item) for item in data.get("matches", [])],
            proximity_edges=[ProximityEdge.from_dict(item) for item in data.get("proximity_edges", [])],
            benchmark_results=[
                BenchmarkResult.from_dict(item) for item in data.get("benchmark_results", [])
            ],
            meta_reviews=[MetaReview.from_dict(item) for item in data.get("meta_reviews", [])],
            context_snapshots=[
                ContextSnapshot.from_dict(item) for item in data.get("context_snapshots", [])
            ],
            safety=SafetyDecision.from_dict(safety_data) if safety_data else None,
        )
