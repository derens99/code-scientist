from code_scientist.models import (
    BenchmarkResult,
    ContextSnapshot,
    Evidence,
    Hypothesis,
    ProximityEdge,
    ResearchGoal,
    ResearchPlanConfig,
    RunState,
    TestPlan,
)


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
    plan = ResearchPlanConfig.from_goal(goal)
    evidence = Evidence(
        id="ev-1",
        kind="paper_excerpt",
        source="2502.18864.pdf",
        content="Generate, debate, and evolve hypotheses.",
        notes="Architecture seed",
    )
    state = RunState(
        goal=goal,
        plan=plan,
        evidence=[evidence],
        proximity_edges=[ProximityEdge("hyp-1", "hyp-2", 0.75)],
        context_snapshots=[
            ContextSnapshot(
                id="ctx-1",
                cycle=1,
                generated_total=2,
                accepted_total=2,
                review_total=2,
                match_total=1,
                meta_review_total=1,
                top_hypothesis_ids=["hyp-1"],
                origin_counts={"generation": 2},
                status_counts={"accepted": 2},
                proximity_edge_count=1,
                scheduler_weights={"ranking": 1.5},
                next_actions=["run_proximity_guided_tournament_matches"],
            )
        ],
    )

    restored = RunState.from_dict(state.to_dict())

    assert restored.goal.objective == "Improve LLM coding agents"
    assert restored.plan == plan
    assert restored.evidence[0].source == "2502.18864.pdf"
    assert restored.proximity_edges[0].similarity == 0.75
    assert restored.context_snapshots[0].next_actions == ["run_proximity_guided_tournament_matches"]


def test_run_state_round_trips_benchmark_results():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    benchmark = BenchmarkResult(
        id="bench-1",
        name="Seeded workflow comparison",
        source="benchmark.json",
        baseline_metrics={"pass_rate": 0.5, "regression_count": 3.0},
        candidate_metrics={"pass_rate": 0.75, "regression_count": 1.0},
        deltas={"pass_rate": 0.25, "regression_count": -2.0},
        success=True,
        notes=["Local fixture"],
    )

    restored = RunState.from_dict(RunState(goal=goal, benchmark_results=[benchmark]).to_dict())

    assert restored.benchmark_results == [benchmark]


def test_run_state_loads_old_state_without_plan_or_context_memory():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    restored = RunState.from_dict({"goal": goal.to_dict()})

    assert restored.plan is None
    assert restored.proximity_edges == []
    assert restored.context_snapshots == []
    assert restored.benchmark_results == []


def test_hypothesis_copy_helpers_preserve_test_plan_type():
    hypothesis = Hypothesis(
        id="hyp-1",
        title="Critic before edit",
        claim="Assumption critique before editing reduces bad patches.",
        rationale="False assumptions are a common source of bad code edits.",
        assumptions=["The critic can identify false premises."],
        evidence_refs=["ev-1"],
        test_plan=TestPlan(
            experiment="Run baseline and candidate workflows on seeded bug tasks.",
            metrics=["pass_rate", "regression_count"],
            success_condition="Candidate improves pass rate without more regressions.",
        ),
        risks=["Extra latency"],
        origin="generation",
    )

    accepted = hypothesis.with_status("accepted")
    reranked = hypothesis.with_elo(1216.0)

    assert isinstance(accepted.test_plan, TestPlan)
    assert isinstance(reranked.test_plan, TestPlan)
    assert accepted.status == "accepted"
    assert reranked.elo == 1216.0
