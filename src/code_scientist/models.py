from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
        return Hypothesis(**{**self.to_dict(), "status": status})

    def with_elo(self, elo: float) -> Hypothesis:
        return Hypothesis(**{**self.to_dict(), "elo": elo})

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
    def from_dict(cls, data: dict[str, Any]) -> RunState:
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
