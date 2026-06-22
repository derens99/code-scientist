import json

import pytest

from code_scientist.benchmarks import load_benchmark_fixture


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
