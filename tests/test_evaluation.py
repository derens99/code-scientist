import json

import pytest

from code_scientist.evaluation import (
    audit_capability_study_coverage,
    build_capability_review_packet,
    build_feedback_loop_review_packet,
    evaluate_capability,
    evaluate_capability_proxy,
    load_capability_evaluation_fixture,
    load_capability_review_fixture,
    load_feedback_loop_evaluation_fixture,
    load_feedback_loop_review_fixture,
    load_prospective_evaluation_fixture,
    plan_prospective_evaluation,
    record_scaling_curve_point,
    record_prospective_measurement,
    run_prospective_validation_manifest,
    retrospective_benchmark_fixtures,
    summarize_capability_study,
)
from code_scientist.models import (
    BenchmarkResult,
    CapabilityEvaluation,
    FeedbackLoopEvaluation,
    Hypothesis,
    ProspectiveEvaluation,
    ResearchGoal,
    RunState,
    SafetyEvaluationResult,
    TestPlan,
)


def _hypothesis(hypothesis_id: str, elo: float) -> Hypothesis:
    return Hypothesis(
        id=hypothesis_id,
        title=f"Candidate {hypothesis_id}",
        claim="A testable coding-agent improvement.",
        rationale="It targets a measurable workflow weakness.",
        assumptions=["The benchmark covers the weakness."],
        evidence_refs=[],
        test_plan=TestPlan(
            experiment="Run baseline and candidate on repair tasks.",
            metrics=["pass_rate"],
            success_condition="Candidate improves pass rate.",
        ),
        risks=[],
        origin="test",
        elo=elo,
    )


def test_capability_evaluation_compares_baseline_and_correlates_scores():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    low = _hypothesis("hyp-low", 1190)
    mid = _hypothesis("hyp-mid", 1210)
    high = _hypothesis("hyp-high", 1240)

    evaluation = evaluate_capability(
        goal=goal,
        hypotheses=[low, mid, high],
        baseline_name="single_shot_llm",
        baseline_score=0.45,
        human_scores={"hyp-low": 0.2, "hyp-mid": 0.55, "hyp-high": 0.8},
        benchmark_scores={"hyp-low": 0.3, "hyp-mid": 0.5, "hyp-high": 0.72},
    )

    assert evaluation.baseline_name == "single_shot_llm"
    assert evaluation.top_hypothesis_id == "hyp-high"
    assert evaluation.code_scientist_score == 0.8
    assert evaluation.beats_baseline is True
    assert evaluation.elo_human_correlation > 0.9
    assert evaluation.elo_benchmark_correlation > 0.9
    assert evaluation.human_score_count == 3
    assert evaluation.benchmark_score_count == 3
    assert "beats baseline" in evaluation.summary


def test_capability_evaluation_loads_old_state_without_score_counts():
    evaluation = CapabilityEvaluation.from_dict(
        {
            "id": "eval-old",
            "baseline_name": "single_shot_llm",
            "baseline_score": 0.45,
            "code_scientist_score": 0.7,
            "beats_baseline": True,
            "top_hypothesis_id": "hyp-old",
            "elo_human_correlation": 0.0,
            "elo_benchmark_correlation": 0.0,
            "candidate_count": 1,
            "summary": "Old state evaluation.",
        }
    )

    assert evaluation.human_score_count == 0
    assert evaluation.benchmark_score_count == 0


def test_load_capability_evaluation_fixture_scores_by_ids_and_keyword_rules(tmp_path):
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    low = _hypothesis("hyp-low", 1190)
    high = _hypothesis("hyp-high", 1240)
    fixture = tmp_path / "capability.json"
    fixture.write_text(
        json.dumps(
            {
                "baseline_name": "single_shot_llm",
                "baseline_score": 0.55,
                "human_scores": {"hyp-low": 0.2},
                "human_score_rules": [
                    {"contains": "Candidate hyp-high", "score": 0.8},
                ],
                "benchmark_score_rules": [
                    {"contains": ["Candidate hyp-high", "workflow weakness"], "score": 0.75},
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_capability_evaluation_fixture(fixture, goal, [low, high])

    assert evaluation.baseline_name == "single_shot_llm"
    assert evaluation.baseline_score == 0.55
    assert evaluation.code_scientist_score == 0.8
    assert evaluation.beats_baseline is True
    assert evaluation.top_hypothesis_id == "hyp-high"
    assert evaluation.elo_human_correlation == 1.0
    assert evaluation.elo_benchmark_correlation == 0.0
    assert evaluation.human_score_count == 2
    assert evaluation.benchmark_score_count == 1


def test_load_capability_evaluation_fixture_accepts_human_rubric_judgments(tmp_path):
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    low = _hypothesis("hyp-low", 1190)
    high = _hypothesis("hyp-high", 1240)
    fixture = tmp_path / "capability-rubric.json"
    fixture.write_text(
        json.dumps(
            {
                "baseline_name": "single_shot_llm",
                "baseline_score": 0.55,
                "human_rubric_scale": 5,
                "human_rubric_judgments": [
                    {
                        "hypothesis_id": "hyp-low",
                        "reviewer": "expert-a",
                        "scores": {
                            "novelty": 2,
                            "plausibility": 3,
                            "impact": 2,
                            "testability": 3,
                            "safety": 5,
                        },
                        "notes": "Too close to known practice.",
                    },
                    {
                        "hypothesis_id": "hyp-high",
                        "reviewer": "expert-a",
                        "scores": {
                            "novelty": 5,
                            "plausibility": 4,
                            "impact": 5,
                            "testability": 5,
                            "safety": 4,
                        },
                    },
                    {
                        "hypothesis_id": "hyp-high",
                        "reviewer": "expert-b",
                        "scores": {
                            "novelty": 4,
                            "plausibility": 4,
                            "impact": 5,
                            "testability": 4,
                            "safety": 5,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_capability_evaluation_fixture(fixture, goal, [low, high])

    assert evaluation.code_scientist_score == 0.9
    assert evaluation.beats_baseline is True
    assert evaluation.human_score_count == 2
    assert evaluation.human_rubric_judgment_count == 3
    assert evaluation.human_rubric_criteria == ["impact", "novelty", "plausibility", "safety", "testability"]
    assert evaluation.elo_human_correlation == 1.0


def test_load_prospective_evaluation_fixture_records_measured_external_validation(tmp_path):
    low = _hypothesis("hyp-low", 1190)
    high = _hypothesis("hyp-high", 1240)
    fixture = tmp_path / "prospective-validation.json"
    fixture.write_text(
        json.dumps(
            {
                "hypothesis_selector": {"contains": "Candidate hyp-high"},
                "implementation_refs": ["branch/retrieval-validation", "runs/retrieval-benchmark/report.md"],
                "baseline_metrics": {"pass_rate": 0.48, "regression_count": 2},
                "measured_metrics": {"pass_rate": 0.71, "regression_count": 1},
                "success_metric": "pass_rate",
                "measurement_source": "held_out_repair_suite",
                "notes": ["Measured by replaying a held-out coding-agent repair suite."],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_prospective_evaluation_fixture(fixture, [low, high])

    assert evaluation.hypothesis_id == "hyp-high"
    assert evaluation.status == "measured"
    assert evaluation.implementation_refs == ["branch/retrieval-validation", "runs/retrieval-benchmark/report.md"]
    assert evaluation.baseline_metrics == {"pass_rate": 0.48, "regression_count": 2.0}
    assert evaluation.measured_metrics == {"pass_rate": 0.71, "regression_count": 1.0}
    assert evaluation.deltas == {"pass_rate": 0.23, "regression_count": -1.0}
    assert evaluation.success is True
    assert evaluation.measurement_source == "held_out_repair_suite"
    assert evaluation.measurement_status == "measured"
    assert evaluation.notes == ["Measured by replaying a held-out coding-agent repair suite."]


def test_run_prospective_validation_manifest_rejects_shell_string_commands(tmp_path):
    hypothesis = _hypothesis("hyp-validation", 1240)
    state = RunState(goal=ResearchGoal.from_objective("Improve validation safety"), hypotheses=[hypothesis])
    manifest = tmp_path / "prospective-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "hypothesis_id": "hyp-validation",
                "implementation_refs": ["branches/validation"],
                "baseline_metrics": {"pass_rate": 0.4},
                "success_metric": "pass_rate",
                "command": "python runner.py",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="command must be a non-empty list"):
        run_prospective_validation_manifest(manifest, state, work_dir=tmp_path / "work")


def test_load_feedback_loop_evaluation_fixture_records_external_measurement(tmp_path):
    fixture = tmp_path / "feedback-loop-validation.json"
    fixture.write_text(
        json.dumps(
            {
                "cycle": 3,
                "source_meta_review_id": "meta-review-2",
                "feedback_agents": ["generation", "ranking"],
                "feedback_item_count": 4,
                "adopted_feedback_count": 3,
                "baseline_quality": {"expert_score": 0.52, "accepted_total": 2},
                "observed_quality": {"expert_score": 0.74, "accepted_total": 4},
                "artifact_refs": ["runs/ablation/baseline.json", "runs/ablation/feedback.json"],
                "measurement_source": "maintainer_blind_review",
                "summary": "Blind maintainer review improved after targeted meta-review feedback.",
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_feedback_loop_evaluation_fixture(fixture)

    assert evaluation.source_meta_review_id == "meta-review-2"
    assert evaluation.feedback_agents == ["generation", "ranking"]
    assert evaluation.adoption_rate == 0.75
    assert evaluation.baseline_quality == {"expert_score": 0.52, "accepted_total": 2.0}
    assert evaluation.observed_quality == {"expert_score": 0.74, "accepted_total": 4.0}
    assert evaluation.deltas == {"expert_score": 0.22, "accepted_total": 2.0}
    assert evaluation.measurement_source == "maintainer_blind_review"
    assert evaluation.measurement_status == "measured"
    assert "Blind maintainer review improved" in evaluation.summary


def test_load_feedback_loop_review_fixture_aggregates_blind_item_scores(tmp_path):
    fixture = tmp_path / "feedback-loop-review.json"
    fixture.write_text(
        json.dumps(
            {
                "cycle": 4,
                "source_meta_review_id": "meta-review-3",
                "feedback_agents": ["generation", "ranking"],
                "feedback_item_count": 4,
                "adopted_feedback_count": 3,
                "measurement_source": "maintainer_blind_review",
                "artifact_refs": ["review-packet.json", "reviewer-scores.json"],
                "review_items": [
                    {
                        "item_id": "item-1",
                        "baseline_label": "arm_red",
                        "observed_label": "arm_blue",
                        "scores": {
                            "arm_red": {"expert_score": 3, "accepted": 0},
                            "arm_blue": {"expert_score": 5, "accepted": 1},
                        },
                    },
                    {
                        "item_id": "item-2",
                        "baseline_label": "arm_blue",
                        "observed_label": "arm_red",
                        "scores": {
                            "arm_blue": {"expert_score": 4, "accepted": 0},
                            "arm_red": {"expert_score": 5, "accepted": 1},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_feedback_loop_review_fixture(fixture)

    assert evaluation.source_meta_review_id == "meta-review-3"
    assert evaluation.feedback_agents == ["generation", "ranking"]
    assert evaluation.feedback_item_count == 4
    assert evaluation.adopted_feedback_count == 3
    assert evaluation.adoption_rate == 0.75
    assert evaluation.baseline_quality == {"accepted": 0.0, "expert_score": 3.5}
    assert evaluation.observed_quality == {"accepted": 1.0, "expert_score": 5.0}
    assert evaluation.deltas == {"accepted": 1.0, "expert_score": 1.5}
    assert evaluation.measurement_source == "maintainer_blind_review"
    assert evaluation.measurement_status == "measured"
    assert "Blind feedback-loop review" in evaluation.summary


def test_build_feedback_loop_review_packet_blinds_arms_and_scores_with_answer_key(tmp_path):
    spec = {
        "cycle": 5,
        "source_meta_review_id": "meta-review-4",
        "feedback_agents": ["generation", "ranking"],
        "feedback_item_count": 2,
        "adopted_feedback_count": 1,
        "measurement_source": "maintainer_blind_review",
        "metrics": ["expert_score", "accepted"],
        "artifact_refs": ["runs/baseline/state.json", "runs/feedback/state.json"],
        "review_items": [
            {
                "item_id": "item-1",
                "prompt": "Which candidate should continue to deeper validation?",
                "baseline_artifact": {
                    "title": "Candidate One",
                    "claim": "Use local summaries before editing.",
                },
                "observed_artifact": {
                    "title": "Candidate Two",
                    "claim": "Use meta-review feedback before editing.",
                },
            }
        ],
    }

    packet, answer_key, score_template = build_feedback_loop_review_packet(spec, seed="paper-gap")

    item = packet["review_items"][0]
    key_item = answer_key["answer_key"]["item-1"]
    template_item = score_template["review_items"][0]
    assert item["item_id"] == "item-1"
    assert set(item["arms"]) == {"arm_a", "arm_b"}
    assert "baseline_label" not in item
    assert "observed_label" not in item
    assert key_item["baseline_label"] in {"arm_a", "arm_b"}
    assert key_item["observed_label"] in {"arm_a", "arm_b"}
    assert key_item["baseline_label"] != key_item["observed_label"]
    assert template_item["scores"] == {
        "arm_a": {"expert_score": None, "accepted": None},
        "arm_b": {"expert_score": None, "accepted": None},
    }

    scored_item = {
        "item_id": "item-1",
        "scores": {
            key_item["baseline_label"]: {"expert_score": 3, "accepted": 0},
            key_item["observed_label"]: {"expert_score": 5, "accepted": 1},
        },
    }
    scored_fixture = tmp_path / "scored-review.json"
    scored_fixture.write_text(
        json.dumps(
            {
                **score_template,
                "answer_key": answer_key["answer_key"],
                "review_items": [scored_item],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_feedback_loop_review_fixture(scored_fixture)

    assert evaluation.source_meta_review_id == "meta-review-4"
    assert evaluation.feedback_agents == ["generation", "ranking"]
    assert evaluation.feedback_item_count == 2
    assert evaluation.adopted_feedback_count == 1
    assert evaluation.baseline_quality == {"accepted": 0.0, "expert_score": 3.0}
    assert evaluation.observed_quality == {"accepted": 1.0, "expert_score": 5.0}
    assert evaluation.deltas == {"accepted": 1.0, "expert_score": 2.0}
    assert evaluation.artifact_refs == ["runs/baseline/state.json", "runs/feedback/state.json"]


def test_build_capability_review_packet_blinds_baseline_and_code_scientist_arms():
    spec = {
        "goal_id": "goal-1",
        "objective": "Improve coding-agent research loops.",
        "baseline_name": "single_shot_llm",
        "metrics": ["novelty", "plausibility", "impact", "testability", "safety"],
        "artifact_refs": ["runs/baseline/state.json", "runs/code-scientist/state.json"],
        "review_items": [
            {
                "item_id": "hyp-1",
                "prompt": "Score each arm against the rubric.",
                "baseline_artifact": {"title": "Baseline", "claim": "Use one prompt."},
                "code_scientist_artifact": {
                    "hypothesis_id": "hyp-1",
                    "title": "Code Scientist",
                    "claim": "Use retrieved evidence and critique loops.",
                },
            }
        ],
    }

    packet, answer_key, score_template = build_capability_review_packet(spec, seed="paper-gap")

    item = packet["review_items"][0]
    key_item = answer_key["answer_key"]["hyp-1"]
    template_item = score_template["review_items"][0]
    assert packet["goal_id"] == "goal-1"
    assert packet["baseline_name"] == "single_shot_llm"
    assert set(item["arms"]) == {"arm_a", "arm_b"}
    assert "baseline_label" not in item
    assert "code_scientist_label" not in item
    assert key_item["baseline_label"] in {"arm_a", "arm_b"}
    assert key_item["code_scientist_label"] in {"arm_a", "arm_b"}
    assert key_item["baseline_label"] != key_item["code_scientist_label"]
    assert key_item["hypothesis_id"] == "hyp-1"
    assert template_item["scores"] == {
        "arm_a": {"novelty": None, "plausibility": None, "impact": None, "testability": None, "safety": None},
        "arm_b": {"novelty": None, "plausibility": None, "impact": None, "testability": None, "safety": None},
    }


def test_load_capability_review_fixture_unblinds_scored_arm_scores(tmp_path):
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    low = _hypothesis("hyp-low", 1190)
    high = _hypothesis("hyp-high", 1240)
    spec = {
        "goal_id": goal.id,
        "objective": goal.objective,
        "baseline_name": "single_shot_llm",
        "human_rubric_scale": 5,
        "metrics": ["novelty", "impact"],
        "review_items": [
            {
                "item_id": "review-1",
                "baseline_artifact": {"title": "Baseline", "claim": "Use one prompt."},
                "code_scientist_artifact": {
                    "hypothesis_id": "hyp-high",
                    "title": "Code Scientist",
                    "claim": "Use retrieved evidence and critique loops.",
                },
            }
        ],
    }
    _, answer_key, score_template = build_capability_review_packet(spec, seed="paper-gap")
    key_item = answer_key["answer_key"]["review-1"]
    scored_fixture = tmp_path / "scored-capability-review.json"
    scored_fixture.write_text(
        json.dumps(
            {
                **score_template,
                "answer_key": answer_key["answer_key"],
                "human_rubric_scale": 5,
                "review_items": [
                    {
                        "item_id": "review-1",
                        "scores": {
                            key_item["baseline_label"]: {"novelty": 3, "impact": 3},
                            key_item["code_scientist_label"]: {"novelty": 5, "impact": 4},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_capability_review_fixture(scored_fixture, goal, [low, high])

    assert evaluation.baseline_name == "single_shot_llm"
    assert evaluation.baseline_score == 0.6
    assert evaluation.code_scientist_score == 0.9
    assert evaluation.beats_baseline is True
    assert evaluation.human_score_count == 1
    assert evaluation.human_rubric_judgment_count == 1
    assert evaluation.human_rubric_criteria == ["impact", "novelty"]
    assert evaluation.elo_human_correlation == 0.0


def test_retrospective_benchmark_fixtures_cover_known_coding_agent_improvements():
    fixtures = retrospective_benchmark_fixtures()

    names = {fixture.name for fixture in fixtures}
    assert "Test-first repair loop" in names
    assert "Retrieval-grounded context selection" in names
    assert "Critic-before-edit assumption audit" in names
    assert all("pass_rate" in fixture.baseline_metrics for fixture in fixtures)
    assert all("regression_count" in fixture.candidate_metrics for fixture in fixtures)
    assert all(fixture.success for fixture in fixtures)


def test_prospective_evaluation_records_measurements_and_deltas():
    hypothesis = _hypothesis("hyp-prospect", 1230)
    planned = plan_prospective_evaluation(
        hypothesis,
        implementation_refs=["branch/candidate-workflow"],
        baseline_metrics={"pass_rate": 0.5, "regression_count": 2.0},
    )

    measured = record_prospective_measurement(
        planned,
        measured_metrics={"pass_rate": 0.7, "regression_count": 1.0},
        success_metric="pass_rate",
    )

    assert planned.status == "planned"
    assert planned.measurement_source == "proxy"
    assert planned.measurement_status == "planned"
    assert measured.status == "measured"
    assert measured.measurement_source == "external_fixture"
    assert measured.measurement_status == "measured"
    assert measured.deltas == {"pass_rate": 0.2, "regression_count": -1.0}
    assert measured.success is True


def test_scaling_curve_point_records_cycle_task_and_budget_delta():
    point = record_scaling_curve_point(
        label="cycles-2-tools-20",
        cycles=2,
        task_count=18,
        tool_budget=20,
        baseline_score=0.45,
        code_scientist_score=0.61,
        notes=["Two-cycle deterministic run."],
    )

    assert point.cycles == 2
    assert point.task_count == 18
    assert point.tool_budget == 20
    assert point.delta == 0.16
    assert point.notes == ["Two-cycle deterministic run."]


def test_capability_study_summary_aggregates_baseline_scaling_and_prospective_results():
    evaluations = [
        CapabilityEvaluation(
            id="eval-1",
            baseline_name="single_shot_llm",
            baseline_score=0.45,
            code_scientist_score=0.72,
            beats_baseline=True,
            top_hypothesis_id="hyp-high",
            elo_human_correlation=0.91,
            elo_benchmark_correlation=0.88,
            candidate_count=4,
            summary="Code Scientist beats baseline.",
        ),
        CapabilityEvaluation(
            id="eval-2",
            baseline_name="single_shot_llm",
            baseline_score=0.6,
            code_scientist_score=0.52,
            beats_baseline=False,
            top_hypothesis_id="hyp-mid",
            elo_human_correlation=0.4,
            elo_benchmark_correlation=0.2,
            candidate_count=4,
            summary="Code Scientist trails baseline.",
        ),
    ]
    scaling = [
        record_scaling_curve_point(
            label="cycles-1",
            cycles=1,
            task_count=9,
            tool_budget=5,
            baseline_score=0.45,
            code_scientist_score=0.56,
        ),
        record_scaling_curve_point(
            label="cycles-2",
            cycles=2,
            task_count=18,
            tool_budget=10,
            baseline_score=0.45,
            code_scientist_score=0.64,
        ),
    ]
    prospective = [
        ProspectiveEvaluation(
            id="prospect-1",
            hypothesis_id="hyp-high",
            status="measured",
            implementation_refs=["branch/high"],
            baseline_metrics={"pass_rate": 0.5},
            measured_metrics={"pass_rate": 0.7},
            deltas={"pass_rate": 0.2},
            success=True,
        ),
        ProspectiveEvaluation(
            id="prospect-2",
            hypothesis_id="hyp-mid",
            status="measured",
            implementation_refs=["branch/mid"],
            baseline_metrics={"pass_rate": 0.5},
            measured_metrics={"pass_rate": 0.47},
            deltas={"pass_rate": -0.03},
            success=False,
        ),
    ]

    summary = summarize_capability_study(evaluations, scaling, prospective)

    assert summary.evaluation_count == 2
    assert summary.baseline_win_rate == 0.5
    assert summary.mean_score_delta == 0.095
    assert summary.mean_elo_human_correlation == 0.655
    assert summary.mean_elo_benchmark_correlation == 0.54
    assert summary.scaling_point_count == 2
    assert summary.scaling_delta_trend == 0.08
    assert summary.prospective_success_rate == 0.5
    assert "win rate 0.500" in summary.summary


def test_capability_study_summary_reports_score_delta_statistics():
    evaluations = [
        CapabilityEvaluation(
            id=f"eval-{index}",
            baseline_name="single_shot_llm",
            baseline_score=0.5,
            code_scientist_score=0.5 + delta,
            beats_baseline=True,
            top_hypothesis_id=f"hyp-{index}",
            elo_human_correlation=0.0,
            elo_benchmark_correlation=0.0,
            candidate_count=4,
            summary="Code Scientist beats baseline.",
        )
        for index, delta in enumerate([0.1, 0.2, 0.3, 0.4], start=1)
    ]

    summary = summarize_capability_study(evaluations, [], [])

    assert summary.score_delta_count == 4
    assert summary.score_delta_stddev == 0.129
    assert summary.score_delta_standard_error == 0.065
    assert summary.score_delta_ci_low == 0.123
    assert summary.score_delta_ci_high == 0.377
    assert summary.score_delta_effect_size == 1.936
    assert summary.baseline_win_sign_test_p_value == 0.125


def test_capability_study_summary_aggregates_feedback_loop_efficacy():
    measured_first = FeedbackLoopEvaluation(
        id="feedback-loop-1",
        cycle=2,
        source_meta_review_id="meta-1",
        feedback_agents=["generation"],
        feedback_item_count=3,
        adopted_feedback_count=2,
        adoption_rate=0.667,
        baseline_quality={"accepted": 0.0, "expert_score": 0.5},
        observed_quality={"accepted": 1.0, "expert_score": 0.7},
        deltas={"accepted": 1.0, "expert_score": 0.2},
        measurement_source="maintainer_blind_review",
        measurement_status="measured",
    )
    measured_second = FeedbackLoopEvaluation(
        id="feedback-loop-2",
        cycle=3,
        source_meta_review_id="meta-2",
        feedback_agents=["reflection"],
        feedback_item_count=2,
        adopted_feedback_count=1,
        adoption_rate=0.5,
        baseline_quality={"accepted": 1.0, "expert_score": 0.6},
        observed_quality={"accepted": 1.0, "expert_score": 0.72},
        deltas={"accepted": 0.0, "expert_score": 0.12},
        measurement_source="maintainer_blind_review",
        measurement_status="measured",
    )
    proxy = FeedbackLoopEvaluation(
        id="feedback-loop-proxy",
        cycle=3,
        source_meta_review_id="meta-proxy",
        feedback_agents=["ranking"],
        feedback_item_count=1,
        adopted_feedback_count=1,
        adoption_rate=1.0,
        baseline_quality={"expert_score": 0.4},
        observed_quality={"expert_score": 0.9},
        deltas={"expert_score": 0.5},
        measurement_source="proxy",
        measurement_status="proxy",
    )

    summary = summarize_capability_study([], [], [], [measured_first, measured_second, proxy])

    assert summary.feedback_loop_measurement_count == 2
    assert summary.feedback_loop_positive_rate == 1.0
    assert summary.feedback_loop_mean_delta == 0.33
    assert summary.feedback_loop_metric_deltas == {"accepted": 0.5, "expert_score": 0.16}
    assert "feedback-loop positive rate 1.000" in summary.summary


def test_capability_study_coverage_audits_paper_evaluation_requirements():
    complete = RunState(
        goal=ResearchGoal.from_objective("Improve LLM coding agents with retrieval"),
        capability_evaluations=[
            CapabilityEvaluation(
                id="eval-1",
                baseline_name="single_shot_llm",
                baseline_score=0.45,
                code_scientist_score=0.72,
                beats_baseline=True,
                top_hypothesis_id="hyp-high",
                elo_human_correlation=0.91,
                elo_benchmark_correlation=0.88,
                candidate_count=4,
                summary="Code Scientist beats baseline.",
                human_score_count=4,
                benchmark_score_count=0,
                human_rubric_judgment_count=4,
                human_rubric_criteria=["impact", "novelty", "plausibility", "safety", "testability"],
                human_preference_judgment_count=4,
                human_preference_win_rate=0.75,
            )
        ],
        benchmark_results=[
            BenchmarkResult(
                id="bench-1",
                name="External repair benchmark",
                source="external-benchmark.json",
                baseline_metrics={
                    "pass_rate": 0.45,
                    "regression_count": 2.0,
                    "tool_calls": 8.0,
                    "wall_time": 6.0,
                    "cost": 0.2,
                },
                candidate_metrics={
                    "pass_rate": 0.72,
                    "regression_count": 1.0,
                    "tool_calls": 9.0,
                    "wall_time": 7.0,
                    "cost": 0.24,
                },
                deltas={
                    "pass_rate": 0.27,
                    "regression_count": -1.0,
                    "tool_calls": 1.0,
                    "wall_time": 1.0,
                    "cost": 0.04,
                },
                success=True,
            )
        ],
        scaling_curve=[
            record_scaling_curve_point("cycles-1", 1, 8, 5, 0.45, 0.56),
            record_scaling_curve_point("cycles-2", 2, 16, 10, 0.45, 0.64),
        ],
        prospective_evaluations=[
            ProspectiveEvaluation(
                id="prospect-1",
                hypothesis_id="hyp-high",
                status="measured",
                implementation_refs=["branch/high"],
                baseline_metrics={"pass_rate": 0.5},
                measured_metrics={"pass_rate": 0.7},
                deltas={"pass_rate": 0.2},
                success=True,
                measurement_source="held_out_repair_suite",
                measurement_status="measured",
            )
        ],
        safety_evaluations=[
            SafetyEvaluationResult(
                id="safety-1",
                suite_name="coding_agent_safety_red_team",
                case_count=4,
                passed_count=4,
                failed_count=0,
                pass_rate=1.0,
            )
        ],
        feedback_loop_evaluations=[
            FeedbackLoopEvaluation(
                id="feedback-loop-1",
                cycle=2,
                source_meta_review_id="meta-1",
                feedback_agents=["generation"],
                feedback_item_count=2,
                adopted_feedback_count=2,
                adoption_rate=1.0,
                baseline_quality={"expert_score": 0.5},
                observed_quality={"expert_score": 0.7},
                deltas={"expert_score": 0.2},
                measurement_source="maintainer_blind_review",
                measurement_status="measured",
            )
        ],
    )
    sparse = RunState(goal=ResearchGoal.from_objective("Improve LLM coding agents with review"))

    complete_coverage = audit_capability_study_coverage([complete, sparse])
    sparse_coverage = audit_capability_study_coverage([sparse])

    assert complete_coverage.run_count == 2
    assert complete_coverage.unique_goal_count == 2
    assert complete_coverage.baseline_names == ["single_shot_llm"]
    assert complete_coverage.human_scored_candidate_count == 4
    assert complete_coverage.benchmark_scored_candidate_count == 0
    assert complete_coverage.benchmark_result_count == 1
    assert complete_coverage.human_rubric_judgment_count == 4
    assert complete_coverage.human_preference_judgment_count == 4
    assert complete_coverage.measured_prospective_count == 1
    assert complete_coverage.safety_evaluation_count == 1
    assert complete_coverage.measured_feedback_loop_count == 1
    assert complete_coverage.passed is True
    assert complete_coverage.missing_requirements == []
    assert sparse_coverage.passed is False
    assert "human rubric scores" in sparse_coverage.missing_requirements
    assert "criterion-level human rubric judgments" in sparse_coverage.missing_requirements
    assert "human preference judgments" in sparse_coverage.missing_requirements
    assert "benchmark scores or benchmark result artifacts" in sparse_coverage.missing_requirements
    assert "multi-goal study" in sparse_coverage.missing_requirements
    assert "external feedback-loop measurement" in sparse_coverage.missing_requirements


def test_capability_study_coverage_requires_external_prospective_measurement():
    proxy_state = RunState(
        goal=ResearchGoal.from_objective("Improve LLM coding agents with local replay"),
        prospective_evaluations=[
            ProspectiveEvaluation(
                id="prospect-proxy",
                hypothesis_id="hyp-proxy",
                status="measured",
                implementation_refs=["branch/proxy"],
                baseline_metrics={"pass_rate": 0.5},
                measured_metrics={"pass_rate": 0.7},
                deltas={"pass_rate": 0.2},
                success=True,
                measurement_source="proxy",
                measurement_status="measured",
            )
        ],
    )

    coverage = audit_capability_study_coverage([proxy_state])

    assert coverage.measured_prospective_count == 0
    assert "prospective/external validation measurements" in coverage.missing_requirements


def test_auto_capability_evaluation_scores_ranked_hypotheses_without_external_counts():
    goal = ResearchGoal.from_objective("Improve LLM coding agents with retrieval")
    low = Hypothesis(
        id="hyp-low",
        title="Thin idea",
        claim="Try another prompt.",
        rationale="No retrieved evidence yet.",
        assumptions=["Prompt wording matters."],
        evidence_refs=[],
        test_plan=TestPlan(
            experiment="Manual smoke test",
            metrics=[],
            success_condition="Looks better",
        ),
        risks=["Too generic."],
        origin="generation",
        elo=1180,
        status="candidate",
    )
    high = Hypothesis(
        id="hyp-high",
        title="Benchmark-grounded verifier",
        claim="Use retrieved benchmark traces and regression counts before accepting patches.",
        rationale="Evidence-backed verification should improve pass_rate without increasing regression_count.",
        assumptions=["Benchmark traces are representative."],
        evidence_refs=["ev-benchmark"],
        test_plan=TestPlan(
            experiment="Run repair benchmark with and without verification.",
            metrics=["pass_rate", "regression_count"],
            success_condition="pass_rate improves and regression_count does not increase",
        ),
        risks=["May overfit to benchmark traces."],
        origin="generation",
        elo=1460,
        status="accepted",
    )

    evaluation = evaluate_capability_proxy(
        goal=goal,
        hypotheses=[low, high],
        baseline_name="single_shot_llm",
        baseline_score=0.45,
    )

    assert evaluation.baseline_name == "single_shot_llm"
    assert evaluation.baseline_score == 0.45
    assert evaluation.top_hypothesis_id == "hyp-high"
    assert evaluation.code_scientist_score > evaluation.baseline_score
    assert evaluation.beats_baseline is True
    assert evaluation.human_score_count == 0
    assert evaluation.benchmark_score_count == 0
    assert "Deterministic proxy" in evaluation.summary
