from __future__ import annotations

from code_scientist.models import Hypothesis, ResearchGoal, RunState, TestPlan, stable_id


def run_baseline_research(
    objective: str,
    *,
    method: str = "single_shot",
    max_hypotheses: int = 1,
) -> RunState:
    baseline_method = method.strip() or "single_shot"
    if baseline_method != "single_shot":
        raise ValueError(f"Unsupported baseline method: {method}")
    if max_hypotheses < 1:
        raise ValueError("max_hypotheses must be at least 1.")

    goal = ResearchGoal.from_objective(objective)
    hypotheses = [
        _single_shot_hypothesis(goal, index)
        for index in range(1, max_hypotheses + 1)
    ]
    return RunState(
        goal=goal,
        run_status="completed",
        hypotheses=hypotheses,
    )


def _single_shot_hypothesis(goal: ResearchGoal, index: int) -> Hypothesis:
    identity = f"{goal.id}:single_shot:{index}:{goal.objective}"
    ordinal = f"Candidate {index}"
    return Hypothesis(
        id=stable_id("baseline", identity),
        title=f"Single-shot baseline {ordinal.lower()}",
        claim="Use a single-pass response to propose an improvement for the requested objective.",
        rationale=(
            "This baseline intentionally omits Code Scientist's retrieval, review, "
            "ranking, evolution, and meta-review loop."
        ),
        assumptions=[
            "A single prompt can produce a plausible research candidate.",
            "No iterative critique or benchmark feedback is used before scoring.",
        ],
        evidence_refs=[],
        test_plan=TestPlan(
            experiment="Score this single-shot candidate against the same benchmark suite as Code Scientist.",
            metrics=["pass_rate", "regression_count"],
            success_condition="Matches or exceeds the benchmark pass rate without additional regressions.",
        ),
        risks=[
            "May miss evidence-grounded mechanisms that require retrieval or review.",
            "May overfit to objective wording rather than benchmark behavior.",
        ],
        origin="baseline:single_shot",
        generation_trace=[
            "Baseline method: single_shot",
            f"Objective: {goal.objective}",
            f"Candidate index: {index}",
        ],
    )
