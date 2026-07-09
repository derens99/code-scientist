from __future__ import annotations

import json
from dataclasses import replace

from code_scientist.agents import GenerationAgent
from code_scientist.concordance import grade_hypotheses, load_objective_benchmark
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
