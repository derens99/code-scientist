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
