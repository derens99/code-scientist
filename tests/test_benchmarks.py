import json
import sys

import pytest

from code_scientist.benchmarks import (
    load_benchmark_fixture,
    run_external_benchmark_comparison,
    run_benchmark_suite,
    run_benchmark_suite_comparison,
    summarize_benchmark_comparison_study,
)
from code_scientist.models import BenchmarkResult, Hypothesis, TestPlan


def test_load_benchmark_fixture_computes_metric_deltas(tmp_path):
    fixture = tmp_path / "benchmark.json"
    fixture.write_text(
        json.dumps(
            {
                "name": "Seeded workflow comparison",
                "baseline": {
                    "pass_rate": 0.5,
                    "regression_count": 3,
                    "tool_calls": 20,
                    "wall_time": 12.5,
                    "cost": 0.4,
                },
                "candidate": {
                    "pass_rate": 0.75,
                    "regression_count": 1,
                    "tool_calls": 18,
                    "wall_time": 10.0,
                    "cost": 0.25,
                },
                "notes": ["Fixture comes from a local smoke benchmark."],
            }
        ),
        encoding="utf-8",
    )

    result = load_benchmark_fixture(fixture)

    assert result.name == "Seeded workflow comparison"
    assert result.source == str(fixture)
    assert result.deltas == {
        "pass_rate": 0.25,
        "regression_count": -2.0,
        "tool_calls": -2.0,
        "wall_time": -2.5,
        "cost": -0.15,
    }
    assert result.success is True
    assert result.notes == ["Fixture comes from a local smoke benchmark."]


def test_load_benchmark_fixture_requires_all_goal_metrics(tmp_path):
    fixture = tmp_path / "benchmark.json"
    fixture.write_text(
        json.dumps(
            {
                "name": "Incomplete comparison",
                "baseline": {"pass_rate": 0.5},
                "candidate": {"pass_rate": 0.75},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing benchmark metrics"):
        load_benchmark_fixture(fixture)


def test_run_benchmark_suite_scores_generated_hypotheses(tmp_path):
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "name": "Coding-agent benchmark suite",
                "baseline": {
                    "pass_rate": 0.25,
                    "regression_count": 2,
                    "tool_calls": 8,
                    "wall_time": 12,
                    "cost": 0.24,
                },
                "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
                "cases": [
                    {"id": "retrieval", "required_terms": ["retrieved evidence", "regression"]},
                    {
                        "id": "blind-review",
                        "required_terms": ["blind review"],
                        "forbidden_terms": ["single prompt"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    hypotheses = [
        Hypothesis(
            id="hyp-retrieval",
            title="Retrieved evidence replay",
            claim="Use retrieved evidence to target regression failures.",
            rationale="Relevant context narrows the repair search.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Replay benchmark failures.",
                metrics=["pass_rate"],
                success_condition="Improve regression pass rate.",
            ),
            risks=[],
            origin="test",
        ),
        Hypothesis(
            id="hyp-review",
            title="Blind review calibration",
            claim="Use blind review to score candidate repairs.",
            rationale="Independent review reduces provenance bias.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Compare blind review scores.",
                metrics=["expert_score"],
                success_condition="Increase expert preference.",
            ),
            risks=[],
            origin="test",
        ),
    ]

    result = run_benchmark_suite(suite, hypotheses)

    assert result.name == "Coding-agent benchmark suite"
    assert result.candidate_metrics["pass_rate"] == 1.0
    assert result.candidate_metrics["regression_count"] == 0.0
    assert result.candidate_metrics["tool_calls"] == 4.0
    assert result.deltas["pass_rate"] == 0.75
    assert result.deltas["regression_count"] == -2.0
    assert result.success is True
    assert "retrieval: passed via hyp-retrieval" in result.notes


def test_run_benchmark_suite_comparison_scores_baseline_and_candidate_hypotheses(tmp_path):
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "name": "Baseline comparison suite",
                "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
                "cases": [
                    {"id": "retrieval", "required_terms": ["retrieved evidence", "regression"]},
                    {
                        "id": "blind-review",
                        "required_terms": ["blind review"],
                        "forbidden_terms": ["single prompt"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    baseline_hypotheses = [
        Hypothesis(
            id="baseline-single-prompt",
            title="Single prompt baseline",
            claim="Use a single prompt to propose candidate repairs.",
            rationale="This baseline does not retrieve evidence or use blind review.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Ask once.",
                metrics=["pass_rate"],
                success_condition="Return a plausible idea.",
            ),
            risks=[],
            origin="baseline",
        )
    ]
    candidate_hypotheses = [
        Hypothesis(
            id="hyp-retrieval",
            title="Retrieved evidence replay",
            claim="Use retrieved evidence to target regression failures.",
            rationale="Relevant context narrows the repair search.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Replay benchmark failures.",
                metrics=["pass_rate"],
                success_condition="Improve regression pass rate.",
            ),
            risks=[],
            origin="test",
        ),
        Hypothesis(
            id="hyp-review",
            title="Blind review calibration",
            claim="Use blind review to score candidate repairs.",
            rationale="Independent review reduces provenance bias.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Compare blind review scores.",
                metrics=["expert_score"],
                success_condition="Increase expert preference.",
            ),
            risks=[],
            origin="test",
        ),
    ]

    result = run_benchmark_suite_comparison(
        suite,
        baseline_hypotheses,
        candidate_hypotheses,
        baseline_name="single_shot",
        candidate_name="code_scientist",
    )

    assert result.name == "Baseline comparison suite"
    assert result.baseline_metrics["pass_rate"] == 0.0
    assert result.baseline_metrics["regression_count"] == 2.0
    assert result.baseline_metrics["tool_calls"] == 4.0
    assert result.candidate_metrics["pass_rate"] == 1.0
    assert result.candidate_metrics["regression_count"] == 0.0
    assert result.candidate_metrics["tool_calls"] == 4.0
    assert result.deltas["pass_rate"] == 1.0
    assert result.deltas["regression_count"] == -2.0
    assert result.success is True
    assert "retrieval: single_shot failed; code_scientist passed via hyp-retrieval" in result.notes


def test_run_external_benchmark_comparison_executes_arm_commands(tmp_path):
    script = tmp_path / "external_runner.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "from pathlib import Path",
                "arm = os.environ['CODE_SCIENTIST_ARM']",
                "hypotheses_path = Path(os.environ['CODE_SCIENTIST_HYPOTHESES_PATH'])",
                "metrics_path = Path(os.environ['CODE_SCIENTIST_METRICS_PATH'])",
                "payload = json.loads(hypotheses_path.read_text(encoding='utf-8'))",
                "hypothesis_count = len(payload['hypotheses'])",
                "pass_rate = 0.25 if arm == 'baseline' else 0.75",
                "metrics = {",
                "    'pass_rate': pass_rate,",
                "    'regression_count': 3 - hypothesis_count,",
                "    'tool_calls': 10 + hypothesis_count,",
                "    'wall_time': 2.5 + hypothesis_count,",
                "    'cost': 0.05 + hypothesis_count / 100,",
                "    'notes': [f'{arm}:{hypothesis_count}:{os.environ.get(\"EXTRA_NOTE\", \"\")}'],",
                "}",
                "metrics_path.write_text(json.dumps(metrics), encoding='utf-8')",
                "print(json.dumps({'ignored': True}))",
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "external-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "External SWE-bench mini",
                "source": "local external fixture",
                "timeout_seconds": 5,
                "env": {"EXTRA_NOTE": "fixture"},
                "baseline": {"command": [sys.executable, str(script)]},
                "candidate": {"command": [sys.executable, str(script)]},
                "notes": ["External benchmark fixture."],
            }
        ),
        encoding="utf-8",
    )
    baseline_hypotheses = [
        Hypothesis(
            id="baseline-hyp",
            title="Single prompt baseline",
            claim="Ask once for an idea.",
            rationale="Baseline output.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Run baseline.",
                metrics=["pass_rate"],
                success_condition="Return an idea.",
            ),
            risks=[],
            origin="baseline",
        )
    ]
    candidate_hypotheses = [
        Hypothesis(
            id="candidate-hyp-1",
            title="Evidence replay",
            claim="Use retrieved benchmark failures.",
            rationale="External failures guide repair.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Replay failures.",
                metrics=["pass_rate"],
                success_condition="Improve pass rate.",
            ),
            risks=[],
            origin="candidate",
        ),
        Hypothesis(
            id="candidate-hyp-2",
            title="Reviewer calibration",
            claim="Calibrate with blind review.",
            rationale="Review reduces bias.",
            assumptions=[],
            evidence_refs=[],
            test_plan=TestPlan(
                experiment="Score blind review.",
                metrics=["expert_score"],
                success_condition="Increase preference.",
            ),
            risks=[],
            origin="candidate",
        ),
    ]
    work_dir = tmp_path / "work"

    result = run_external_benchmark_comparison(
        manifest,
        baseline_hypotheses,
        candidate_hypotheses,
        work_dir=work_dir,
    )

    baseline_input = json.loads((work_dir / "baseline-hypotheses.json").read_text(encoding="utf-8"))
    candidate_input = json.loads((work_dir / "candidate-hypotheses.json").read_text(encoding="utf-8"))
    assert baseline_input["arm"] == "baseline"
    assert baseline_input["hypotheses"][0]["id"] == "baseline-hyp"
    assert candidate_input["arm"] == "candidate"
    assert len(candidate_input["hypotheses"]) == 2
    assert result.name == "External SWE-bench mini"
    assert result.source == str(manifest)
    assert result.baseline_metrics["pass_rate"] == 0.25
    assert result.candidate_metrics["pass_rate"] == 0.75
    assert result.deltas["pass_rate"] == 0.5
    assert result.success is True
    assert "baseline external command completed" in result.notes
    assert "candidate external command completed" in result.notes
    assert "baseline:1:fixture" in result.notes
    assert "candidate:2:fixture" in result.notes


def test_run_external_benchmark_comparison_rejects_shell_string_commands(tmp_path):
    manifest = tmp_path / "external-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "Unsafe shell manifest",
                "baseline": {"command": "python runner.py"},
                "candidate": {"command": [sys.executable, "-c", "print('{}')"]},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="command must be a non-empty list"):
        run_external_benchmark_comparison(manifest, [], [], work_dir=tmp_path / "work")


def test_summarize_benchmark_comparison_study_aggregates_results():
    first = BenchmarkResult(
        id="bench-1",
        name="Retrieval suite",
        source="suite-1.json",
        baseline_metrics={"pass_rate": 0.0, "regression_count": 2.0, "tool_calls": 4.0},
        candidate_metrics={"pass_rate": 1.0, "regression_count": 0.0, "tool_calls": 6.0},
        deltas={
            "pass_rate": 1.0,
            "regression_count": -2.0,
            "tool_calls": 2.0,
            "wall_time": -1.0,
            "cost": 0.02,
        },
        success=True,
    )
    second = BenchmarkResult(
        id="bench-2",
        name="Review suite",
        source="suite-2.json",
        baseline_metrics={"pass_rate": 0.5, "regression_count": 1.0, "tool_calls": 2.0},
        candidate_metrics={"pass_rate": 0.0, "regression_count": 2.0, "tool_calls": 3.0},
        deltas={
            "pass_rate": -0.5,
            "regression_count": 1.0,
            "tool_calls": 1.0,
            "wall_time": 0.0,
            "cost": 0.0,
        },
        success=False,
    )

    summary = summarize_benchmark_comparison_study([first, second])

    assert summary["comparison_count"] == 2
    assert summary["success_count"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["mean_pass_rate_delta"] == 0.25
    assert summary["total_regression_delta"] == -1.0
    assert summary["mean_tool_calls_delta"] == 1.5
    assert summary["mean_wall_time_delta"] == -0.5
    assert summary["mean_cost_delta"] == 0.01
