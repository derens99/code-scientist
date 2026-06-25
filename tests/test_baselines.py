from code_scientist.baselines import run_baseline_research


def test_run_baseline_research_creates_single_shot_state():
    state = run_baseline_research(
        "Improve LLM coding agents with retrieved evidence regression analysis",
        max_hypotheses=2,
    )

    assert state.goal.objective == "Improve LLM coding agents with retrieved evidence regression analysis"
    assert state.run_status == "completed"
    assert len(state.hypotheses) == 2
    assert {hypothesis.origin for hypothesis in state.hypotheses} == {"baseline:single_shot"}
    assert state.hypotheses[0].id.startswith("baseline-")
    assert "Baseline method: single_shot" in state.hypotheses[0].generation_trace
    assert state.hypotheses[0].test_plan.metrics == ["pass_rate", "regression_count"]
    assert state.task_queue == []
    assert state.matches == []
