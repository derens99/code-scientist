from __future__ import annotations

import json
from dataclasses import replace

from code_scientist.agents import GenerationAgent
from code_scientist.concordance import (
    compute_elo_concordance,
    grade_hypotheses,
    load_objective_benchmark,
)
from code_scientist.models import ResearchGoal


def _benchmark_file(tmp_path, **overrides):
    payload = {
        "name": "objective-demo",
        "question": "Which retry strategy fixes the flaky integration test?",
        "answer": "backoff",
        **overrides,
    }
    path = tmp_path / "objective.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_objective_benchmark_validates_required_fields(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    assert benchmark.name == "objective-demo"
    assert benchmark.answer == "backoff"


def test_grade_hypotheses_extracts_declared_answers(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=3)
    correct = replace(base[0], rationale=base[0].rationale + " Answer: backoff")
    wrong = replace(base[1], rationale=base[1].rationale + " Answer: retry-once")
    ungraded = base[2]  # declares no answer

    grades = grade_hypotheses(benchmark, [correct, wrong, ungraded])

    assert grades[correct.id] is True
    assert grades[wrong.id] is False
    assert ungraded.id not in grades


def test_grade_hypotheses_explicit_grades_override_extraction(tmp_path):
    benchmark = load_objective_benchmark(_benchmark_file(tmp_path))
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=2)
    hypothesis = replace(base[0], rationale=base[0].rationale + " Answer: backoff")

    grades = grade_hypotheses(benchmark, [hypothesis, base[1]], grades={hypothesis.id: False, base[1].id: True})

    assert grades[hypothesis.id] is False  # explicit grade wins
    assert grades[base[1].id] is True  # explicit grade covers unextractable hypothesis


def test_compute_elo_concordance_buckets_and_top1(tmp_path):
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=4)
    hyps = [
        replace(base[0], elo=1400.0),  # correct
        replace(base[1], elo=1300.0),  # correct
        replace(base[2], elo=1200.0),  # wrong
        replace(base[3], elo=1100.0),  # wrong
    ]
    correctness = {hyps[0].id: True, hyps[1].id: True, hyps[2].id: False, hyps[3].id: False}

    result = compute_elo_concordance("objective-demo", "Which fix?", hyps, correctness)

    assert result.graded_count == 4
    assert result.overall_accuracy == 0.5
    assert result.top_hypothesis_id == hyps[0].id
    assert result.top_hypothesis_correct is True
    # every (correct, incorrect) pair has the correct one at higher Elo
    assert result.concordance_index == 1.0
    assert len(result.buckets) == 4
    assert result.buckets[0]["accuracy"] == 1.0 and result.buckets[-1]["accuracy"] == 0.0


def test_compute_elo_concordance_handles_ties_and_single_class():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=2)
    hyps = [replace(base[0], elo=1200.0), replace(base[1], elo=1200.0)]

    tie_result = compute_elo_concordance("b", "q", hyps, {hyps[0].id: True, hyps[1].id: False})
    assert tie_result.concordance_index == 0.5  # equal Elo counts half

    single_class = compute_elo_concordance("b", "q", hyps, {hyps[0].id: True, hyps[1].id: True})
    assert single_class.concordance_index == 0.5  # no (correct, incorrect) pairs
    assert single_class.overall_accuracy == 1.0


def test_compute_elo_concordance_excludes_inactive_and_counts_ungraded():
    goal = ResearchGoal.from_objective("Find testable ideas to improve LLM coding agents")
    base = GenerationAgent().generate(goal, [], limit=3)
    quarantined = replace(base[0], elo=1500.0, status="quarantined")
    graded = replace(base[1], elo=1300.0)
    ungraded = replace(base[2], elo=1200.0)

    result = compute_elo_concordance(
        "b", "q", [quarantined, graded, ungraded],
        {quarantined.id: True, graded.id: True},
    )

    assert result.graded_count == 1  # quarantined excluded even though graded
    assert result.ungraded_count == 1  # active but ungraded
    assert result.top_hypothesis_id == graded.id
