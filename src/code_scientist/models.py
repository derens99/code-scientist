from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha1
from typing import Any, ClassVar


def stable_id(prefix: str, text: str) -> str:
    digest = sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


_GOAL_BRIEF_SECTION_ALIASES = {
    "preference": "preferences",
    "preferences": "preferences",
    "proposal preference": "preferences",
    "proposal preferences": "preferences",
    "constraint": "constraints",
    "constraints": "constraints",
    "lab constraint": "constraints",
    "lab constraints": "constraints",
    "metric": "metrics",
    "metrics": "metrics",
    "evaluation metric": "metrics",
    "evaluation metrics": "metrics",
    "safety": "safety_notes",
    "safety note": "safety_notes",
    "safety notes": "safety_notes",
    "allowed source": "allowed_sources",
    "allowed sources": "allowed_sources",
    "source constraint": "allowed_sources",
    "source constraints": "allowed_sources",
    "allowed tool": "allowed_tools",
    "allowed tools": "allowed_tools",
    "tool": "allowed_tools",
    "tools": "allowed_tools",
    "output format": "output_formats",
    "output formats": "output_formats",
    "termination criterion": "termination_criteria",
    "termination criteria": "termination_criteria",
    "stop criterion": "termination_criteria",
    "stop criteria": "termination_criteria",
}


@dataclass(frozen=True)
class ResearchGoal:
    id: str
    objective: str
    domain: str = "ai_llm_code"
    preferences: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    allowed_sources: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    output_formats: list[str] = field(default_factory=list)
    termination_criteria: list[str] = field(default_factory=list)

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

    @classmethod
    def from_objective_with_briefs(cls, objective: str, briefs: list[str]) -> ResearchGoal:
        goal = cls.from_objective(objective)
        sections = _parse_goal_brief_sections(briefs)
        return replace(
            goal,
            preferences=_merge_unique(goal.preferences, sections["preferences"]),
            constraints=_merge_unique(goal.constraints, sections["constraints"]),
            metrics=_merge_unique(goal.metrics, sections["metrics"]),
            safety_notes=_merge_unique(goal.safety_notes, sections["safety_notes"]),
            allowed_sources=_merge_unique(goal.allowed_sources, sections["allowed_sources"]),
            allowed_tools=_merge_unique(goal.allowed_tools, sections["allowed_tools"]),
            output_formats=_merge_unique(goal.output_formats, sections["output_formats"]),
            termination_criteria=_merge_unique(goal.termination_criteria, sections["termination_criteria"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchGoal:
        copied = dict(data)
        copied.setdefault("allowed_sources", [])
        copied.setdefault("allowed_tools", [])
        copied.setdefault("output_formats", [])
        copied.setdefault("termination_criteria", [])
        return cls(**copied)


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
    output_formats: list[str] = field(default_factory=list)
    allowed_sources: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    termination_criteria: list[str] = field(default_factory=list)

    @classmethod
    def from_goal(
        cls,
        goal: ResearchGoal,
        proposal_preferences: list[str] | None = None,
        evaluation_criteria: list[str] | None = None,
        constraints: list[str] | None = None,
        output_formats: list[str] | None = None,
        allowed_sources: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        termination_criteria: list[str] | None = None,
    ) -> ResearchPlanConfig:
        identity = (
            f"{goal.id}:{goal.objective}:{','.join(goal.preferences)}:"
            f"{','.join(goal.constraints)}:{','.join(goal.metrics)}:"
            f"{','.join(goal.allowed_sources)}:{','.join(goal.allowed_tools)}"
        )
        return cls(
            id=stable_id("plan", identity),
            goal_id=goal.id,
            proposal_preferences=proposal_preferences if proposal_preferences is not None else [*goal.preferences],
            evaluation_criteria=evaluation_criteria if evaluation_criteria is not None else [
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
                "evidence_grounding",
            ],
            scheduler_weights={
                "generation": 1.0,
                "reflection": 1.0,
                "proximity": 0.5,
                "ranking": 1.0,
                "evolution": 0.75,
                "meta_review": 0.5,
            },
            constraints=constraints if constraints is not None else [*goal.constraints],
            output_formats=(
                output_formats
                if output_formats is not None
                else goal.output_formats or ["markdown_report", "research_overview"]
            ),
            allowed_sources=(
                allowed_sources
                if allowed_sources is not None
                else goal.allowed_sources or ["seed_paper_evidence", "local_evidence_paths"]
            ),
            allowed_tools=(
                allowed_tools if allowed_tools is not None else goal.allowed_tools or ["deterministic_agents"]
            ),
            termination_criteria=(
                termination_criteria
                if termination_criteria is not None
                else goal.termination_criteria or ["max_cycles", "max_hypotheses", "human_stop"]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchPlanConfig:
        copied = dict(data)
        copied.setdefault("constraints", [])
        copied.setdefault("output_formats", ["markdown_report", "research_overview"])
        copied.setdefault("allowed_sources", ["seed_paper_evidence", "local_evidence_paths"])
        copied.setdefault("allowed_tools", ["deterministic_agents"])
        copied.setdefault("termination_criteria", ["max_cycles", "max_hypotheses", "human_stop"])
        return cls(**copied)


def _parse_goal_brief_sections(briefs: list[str]) -> dict[str, list[str]]:
    sections = {section: [] for section in set(_GOAL_BRIEF_SECTION_ALIASES.values())}
    current_section = ""
    for brief in briefs:
        for raw_line in brief.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading, inline_value = _goal_brief_heading(line)
            if heading:
                current_section = heading
                if inline_value:
                    sections[current_section].extend(_goal_brief_items(inline_value))
                continue
            if current_section:
                sections[current_section].extend(_goal_brief_items(line))
    return {key: _merge_unique([], value) for key, value in sections.items()}


def _goal_brief_heading(line: str) -> tuple[str, str]:
    markdown_heading = line.lstrip("#").strip() if line.startswith("#") else ""
    if markdown_heading:
        section = _GOAL_BRIEF_SECTION_ALIASES.get(_normalize_goal_brief_heading(markdown_heading))
        return (section or "", "")
    if ":" not in line or line.startswith(("-", "*", "+")):
        return "", ""
    heading, value = line.split(":", 1)
    section = _GOAL_BRIEF_SECTION_ALIASES.get(_normalize_goal_brief_heading(heading))
    return (section or "", value.strip() if section else "")


def _normalize_goal_brief_heading(value: str) -> str:
    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _goal_brief_items(line: str) -> list[str]:
    cleaned = line.strip()
    while cleaned and cleaned[0] in "-*+":
        cleaned = cleaned[1:].strip()
    if len(cleaned) > 2 and cleaned[0].isdigit() and cleaned[1] in {".", ")"}:
        cleaned = cleaned[2:].strip()
    return [cleaned] if cleaned else []


def _merge_unique(existing: list[str], additions: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for value in [*existing, *additions]:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            values.append(cleaned)
    return values


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
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        copied = dict(data)
        copied.setdefault("metadata", {})
        return cls(**copied)


@dataclass(frozen=True)
class EvidenceSafetyFinding:
    id: str
    evidence_id: str
    source: str
    allowed: bool
    flags: list[str]
    reason: str
    content_preview: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceSafetyFinding:
        copied = dict(data)
        copied.setdefault("flags", [])
        copied.setdefault("content_preview", "")
        return cls(**copied)


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
    generation_trace: list[str] = field(default_factory=list)
    evolution_trace: list[str] = field(default_factory=list)
    merged_into: str = ""
    proximity_notes: list[str] = field(default_factory=list)
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
        copied.setdefault("generation_trace", [])
        copied.setdefault("evolution_trace", [])
        copied.setdefault("merged_into", "")
        copied.setdefault("proximity_notes", [])
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
    review_type: str = "initial_review"
    evidence_refs: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    review_trace: list[str] = field(default_factory=list)
    confidence: float = 0.5
    requires_revision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Review:
        copied = dict(data)
        copied.setdefault("review_type", "initial_review")
        copied.setdefault("evidence_refs", [])
        copied.setdefault("findings", [])
        copied.setdefault("review_trace", [])
        copied.setdefault("confidence", 0.5)
        copied.setdefault("requires_revision", False)
        return cls(**copied)


@dataclass(frozen=True)
class Match:
    id: str
    hypothesis_a: str
    hypothesis_b: str
    winner: str
    rationale: str
    elo_before: dict[str, float]
    elo_after: dict[str, float]
    comparison_mode: str = "heuristic_pairwise"
    judge_trace: str = ""
    uncertainty: float = 0.0
    review_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    debate_transcript: list[str] = field(default_factory=list)
    outcome: str = "win"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Match:
        copied = dict(data)
        copied.setdefault("comparison_mode", "heuristic_pairwise")
        copied.setdefault("judge_trace", "")
        copied.setdefault("uncertainty", 0.0)
        copied.setdefault("review_refs", [])
        copied.setdefault("evidence_refs", [])
        copied.setdefault("debate_transcript", [])
        copied.setdefault("outcome", "win")
        return cls(**copied)


@dataclass(frozen=True)
class ProximityEdge:
    source: str
    target: str
    similarity: float
    method: str = "lexical_token_overlap"
    reason: str = ""
    cluster_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    review_refs: list[str] = field(default_factory=list)
    deduplication_action: str = ""
    diversity_action: str = ""
    exploration_trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProximityEdge:
        copied = dict(data)
        copied.setdefault("method", "lexical_token_overlap")
        copied.setdefault("reason", "")
        copied.setdefault("cluster_id", "")
        copied.setdefault("evidence_refs", [])
        copied.setdefault("review_refs", [])
        copied.setdefault("deduplication_action", "")
        copied.setdefault("diversity_action", "")
        copied.setdefault("exploration_trace", [])
        return cls(**copied)


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
class CapabilityEvaluation:
    id: str
    baseline_name: str
    baseline_score: float
    code_scientist_score: float
    beats_baseline: bool
    top_hypothesis_id: str
    elo_human_correlation: float
    elo_benchmark_correlation: float
    candidate_count: int
    summary: str
    human_score_count: int = 0
    benchmark_score_count: int = 0
    human_rubric_judgment_count: int = 0
    human_rubric_criteria: list[str] = field(default_factory=list)
    human_preference_judgment_count: int = 0
    human_preference_win_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityEvaluation:
        copied = dict(data)
        copied.setdefault("human_score_count", 0)
        copied.setdefault("benchmark_score_count", 0)
        copied.setdefault("human_rubric_judgment_count", 0)
        copied.setdefault("human_rubric_criteria", [])
        copied.setdefault("human_preference_judgment_count", 0)
        copied.setdefault("human_preference_win_rate", 0.0)
        return cls(**copied)


@dataclass(frozen=True)
class CapabilityStudySummary:
    id: str
    evaluation_count: int
    baseline_win_rate: float
    mean_score_delta: float
    mean_elo_human_correlation: float
    mean_elo_benchmark_correlation: float
    scaling_point_count: int
    scaling_delta_trend: float
    prospective_count: int
    prospective_success_rate: float
    summary: str
    score_delta_count: int = 0
    score_delta_stddev: float = 0.0
    score_delta_standard_error: float = 0.0
    score_delta_ci_low: float = 0.0
    score_delta_ci_high: float = 0.0
    score_delta_effect_size: float = 0.0
    baseline_win_sign_test_p_value: float = 1.0
    feedback_loop_measurement_count: int = 0
    feedback_loop_positive_rate: float = 0.0
    feedback_loop_mean_delta: float = 0.0
    feedback_loop_metric_deltas: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityStudySummary:
        copied = dict(data)
        copied.setdefault("score_delta_count", 0)
        copied.setdefault("score_delta_stddev", 0.0)
        copied.setdefault("score_delta_standard_error", 0.0)
        copied.setdefault("score_delta_ci_low", 0.0)
        copied.setdefault("score_delta_ci_high", 0.0)
        copied.setdefault("score_delta_effect_size", 0.0)
        copied.setdefault("baseline_win_sign_test_p_value", 1.0)
        copied.setdefault("feedback_loop_measurement_count", 0)
        copied.setdefault("feedback_loop_positive_rate", 0.0)
        copied.setdefault("feedback_loop_mean_delta", 0.0)
        copied.setdefault("feedback_loop_metric_deltas", {})
        return cls(**copied)


@dataclass(frozen=True)
class CapabilityStudyCoverage:
    id: str
    run_count: int
    unique_goal_count: int
    baseline_names: list[str]
    capability_evaluation_count: int
    human_scored_candidate_count: int
    benchmark_scored_candidate_count: int
    benchmark_result_count: int
    human_rubric_judgment_count: int
    human_preference_judgment_count: int
    scaling_point_count: int
    measured_prospective_count: int
    measured_feedback_loop_count: int
    safety_evaluation_count: int
    missing_requirements: list[str]
    passed: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityStudyCoverage:
        copied = dict(data)
        copied.setdefault("benchmark_result_count", 0)
        copied.setdefault("human_rubric_judgment_count", 0)
        copied.setdefault("human_preference_judgment_count", 0)
        copied.setdefault("measured_feedback_loop_count", 0)
        copied.setdefault("missing_requirements", [])
        return cls(**copied)


@dataclass(frozen=True)
class ProspectiveEvaluation:
    id: str
    hypothesis_id: str
    status: str
    implementation_refs: list[str]
    baseline_metrics: dict[str, float]
    measured_metrics: dict[str, float]
    deltas: dict[str, float]
    success: bool
    measurement_source: str = "proxy"
    measurement_status: str = "proxy"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProspectiveEvaluation:
        copied = dict(data)
        copied.setdefault("measurement_source", "proxy")
        copied.setdefault("measurement_status", "proxy")
        copied.setdefault("notes", [])
        return cls(**copied)


@dataclass(frozen=True)
class ScalingCurvePoint:
    id: str
    label: str
    cycles: int
    task_count: int
    tool_budget: int
    baseline_score: float
    code_scientist_score: float
    delta: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScalingCurvePoint:
        copied = dict(data)
        copied.setdefault("notes", [])
        return cls(**copied)


@dataclass(frozen=True)
class SafetyEvaluationResult:
    id: str
    suite_name: str
    case_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    failed_case_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SafetyEvaluationResult:
        copied = dict(data)
        copied.setdefault("failed_case_ids", [])
        copied.setdefault("notes", [])
        return cls(**copied)


@dataclass(frozen=True)
class FeedbackLoopEvaluation:
    id: str
    cycle: int
    source_meta_review_id: str
    feedback_agents: list[str]
    feedback_item_count: int
    adopted_feedback_count: int
    adoption_rate: float
    baseline_quality: dict[str, float]
    observed_quality: dict[str, float]
    deltas: dict[str, float]
    artifact_refs: list[str] = field(default_factory=list)
    summary: str = ""
    measurement_source: str = "proxy"
    measurement_status: str = "proxy"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackLoopEvaluation:
        copied = dict(data)
        copied.setdefault("artifact_refs", [])
        copied.setdefault("summary", "")
        copied.setdefault("measurement_source", "proxy")
        copied.setdefault("measurement_status", "proxy")
        return cls(**copied)


@dataclass(frozen=True)
class ResearchOutputArtifact:
    id: str
    output_type: str
    title: str
    summary: str
    sections: dict[str, str]
    related_hypothesis_ids: list[str] = field(default_factory=list)
    contact_targets: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchOutputArtifact:
        copied = dict(data)
        copied.setdefault("related_hypothesis_ids", [])
        copied.setdefault("contact_targets", [])
        copied.setdefault("evidence_refs", [])
        return cls(**copied)


@dataclass(frozen=True)
class MetaReview:
    id: str
    common_weaknesses: list[str]
    safety_concerns: list[str]
    missing_evidence: list[str]
    promising_directions: list[str]
    prompt_feedback: list[str]
    agent_feedback: dict[str, list[str]] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetaReview:
        copied = dict(data)
        copied.setdefault("agent_feedback", {})
        copied.setdefault("evidence_refs", [])
        return cls(**copied)


@dataclass(frozen=True)
class ResearchOverview:
    id: str
    summary: str
    top_hypothesis_ids: list[str]
    promising_directions: list[str]
    next_experiments: list[str]
    limitations: list[str]
    generated_by: str = "meta_review"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchOverview:
        copied = dict(data)
        copied.setdefault("generated_by", "meta_review")
        return cls(**copied)


@dataclass(frozen=True)
class UserFeedback:
    id: str
    kind: str
    target_id: str
    content: str
    influence: str = "informational"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserFeedback:
        copied = dict(data)
        copied.setdefault("influence", "informational")
        return cls(**copied)


@dataclass(frozen=True)
class RetrievalMemoryRecord:
    id: str
    query: str
    retrieval_method: str
    evidence_refs: list[str] = field(default_factory=list)
    cycle: int = 0
    agent: str = ""
    task_id: str = ""
    citations: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrievalMemoryRecord:
        copied = dict(data)
        copied.setdefault("evidence_refs", [])
        copied.setdefault("cycle", 0)
        copied.setdefault("agent", "")
        copied.setdefault("task_id", "")
        copied.setdefault("citations", [])
        copied.setdefault("reason", "")
        return cls(**copied)


@dataclass(frozen=True)
class AgentTrace:
    id: str
    cycle: int
    agent: str
    action: str
    task_id: str = ""
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    status: str = "completed"
    notes: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    llm_interactions: list[dict[str, str]] = field(default_factory=list)
    scratchpad: list[str] = field(default_factory=list)
    transcript_ref: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTrace:
        copied = dict(data)
        copied.setdefault("task_id", "")
        copied.setdefault("input_refs", [])
        copied.setdefault("output_refs", [])
        copied.setdefault("status", "completed")
        copied.setdefault("notes", "")
        copied.setdefault("evidence_refs", [])
        copied.setdefault("llm_interactions", [])
        copied.setdefault("scratchpad", [])
        copied.setdefault("transcript_ref", "")
        copied.setdefault("tool_calls", [])
        return cls(**copied)


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    priority: float
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    attempts: int = 0
    result_refs: list[str] = field(default_factory=list)
    error: str = ""
    worker_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        copied = dict(data)
        copied.setdefault("payload", {})
        copied.setdefault("status", "queued")
        copied.setdefault("attempts", 0)
        copied.setdefault("result_refs", [])
        copied.setdefault("error", "")
        copied.setdefault("worker_state", {})
        return cls(**copied)


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
    run_status: str = "completed"
    plan: ResearchPlanConfig | None = None
    evidence: list[Evidence] = field(default_factory=list)
    evidence_safety_findings: list[EvidenceSafetyFinding] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    proximity_edges: list[ProximityEdge] = field(default_factory=list)
    benchmark_results: list[BenchmarkResult] = field(default_factory=list)
    capability_evaluations: list[CapabilityEvaluation] = field(default_factory=list)
    prospective_evaluations: list[ProspectiveEvaluation] = field(default_factory=list)
    scaling_curve: list[ScalingCurvePoint] = field(default_factory=list)
    safety_evaluations: list[SafetyEvaluationResult] = field(default_factory=list)
    feedback_loop_evaluations: list[FeedbackLoopEvaluation] = field(default_factory=list)
    research_output_artifacts: list[ResearchOutputArtifact] = field(default_factory=list)
    meta_reviews: list[MetaReview] = field(default_factory=list)
    context_snapshots: list[ContextSnapshot] = field(default_factory=list)
    safety: SafetyDecision | None = None
    research_overview: ResearchOverview | None = None
    user_feedback: list[UserFeedback] = field(default_factory=list)
    agent_traces: list[AgentTrace] = field(default_factory=list)
    retrieval_memory: list[RetrievalMemoryRecord] = field(default_factory=list)
    task_queue: list[Task] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "run_status": self.run_status,
            "plan": self.plan.to_dict() if self.plan else None,
            "evidence": [item.to_dict() for item in self.evidence],
            "evidence_safety_findings": [item.to_dict() for item in self.evidence_safety_findings],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "reviews": [item.to_dict() for item in self.reviews],
            "matches": [item.to_dict() for item in self.matches],
            "proximity_edges": [item.to_dict() for item in self.proximity_edges],
            "benchmark_results": [item.to_dict() for item in self.benchmark_results],
            "capability_evaluations": [item.to_dict() for item in self.capability_evaluations],
            "prospective_evaluations": [item.to_dict() for item in self.prospective_evaluations],
            "scaling_curve": [item.to_dict() for item in self.scaling_curve],
            "safety_evaluations": [item.to_dict() for item in self.safety_evaluations],
            "feedback_loop_evaluations": [item.to_dict() for item in self.feedback_loop_evaluations],
            "research_output_artifacts": [item.to_dict() for item in self.research_output_artifacts],
            "meta_reviews": [item.to_dict() for item in self.meta_reviews],
            "context_snapshots": [item.to_dict() for item in self.context_snapshots],
            "safety": self.safety.to_dict() if self.safety else None,
            "research_overview": self.research_overview.to_dict() if self.research_overview else None,
            "user_feedback": [item.to_dict() for item in self.user_feedback],
            "agent_traces": [item.to_dict() for item in self.agent_traces],
            "retrieval_memory": [item.to_dict() for item in self.retrieval_memory],
            "task_queue": [item.to_dict() for item in self.task_queue],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        safety_data = data.get("safety")
        plan_data = data.get("plan")
        return cls(
            goal=ResearchGoal.from_dict(data["goal"]),
            run_status=data.get("run_status", "completed"),
            plan=ResearchPlanConfig.from_dict(plan_data) if plan_data else None,
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            evidence_safety_findings=[
                EvidenceSafetyFinding.from_dict(item)
                for item in data.get("evidence_safety_findings", [])
            ],
            hypotheses=[Hypothesis.from_dict(item) for item in data.get("hypotheses", [])],
            reviews=[Review.from_dict(item) for item in data.get("reviews", [])],
            matches=[Match.from_dict(item) for item in data.get("matches", [])],
            proximity_edges=[ProximityEdge.from_dict(item) for item in data.get("proximity_edges", [])],
            benchmark_results=[
                BenchmarkResult.from_dict(item) for item in data.get("benchmark_results", [])
            ],
            capability_evaluations=[
                CapabilityEvaluation.from_dict(item)
                for item in data.get("capability_evaluations", [])
            ],
            prospective_evaluations=[
                ProspectiveEvaluation.from_dict(item)
                for item in data.get("prospective_evaluations", [])
            ],
            scaling_curve=[
                ScalingCurvePoint.from_dict(item)
                for item in data.get("scaling_curve", [])
            ],
            safety_evaluations=[
                SafetyEvaluationResult.from_dict(item)
                for item in data.get("safety_evaluations", [])
            ],
            feedback_loop_evaluations=[
                FeedbackLoopEvaluation.from_dict(item)
                for item in data.get("feedback_loop_evaluations", [])
            ],
            research_output_artifacts=[
                ResearchOutputArtifact.from_dict(item)
                for item in data.get("research_output_artifacts", [])
            ],
            meta_reviews=[MetaReview.from_dict(item) for item in data.get("meta_reviews", [])],
            context_snapshots=[
                ContextSnapshot.from_dict(item) for item in data.get("context_snapshots", [])
            ],
            safety=SafetyDecision.from_dict(safety_data) if safety_data else None,
            research_overview=(
                ResearchOverview.from_dict(data["research_overview"])
                if data.get("research_overview")
                else None
            ),
            user_feedback=[UserFeedback.from_dict(item) for item in data.get("user_feedback", [])],
            agent_traces=[AgentTrace.from_dict(item) for item in data.get("agent_traces", [])],
            retrieval_memory=[
                RetrievalMemoryRecord.from_dict(item)
                for item in data.get("retrieval_memory", [])
            ],
            task_queue=[Task.from_dict(item) for item in data.get("task_queue", [])],
        )
