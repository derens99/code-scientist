from code_scientist.reporting import render_report
from code_scientist.models import BenchmarkResult
from code_scientist.supervisor import run_research_cycle


def test_render_report_includes_leaderboard_and_limitations(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=2,
        out_dir=tmp_path / "run",
    )

    report = render_report(state)

    assert "# Code Scientist Research Report" in report
    assert "Research Plan Configuration" in report
    assert "Context Memory" in report
    assert "Proximity Graph" in report
    assert "Ranked Hypotheses" in report
    assert "Elo is an auto-evaluation proxy" in report
    assert "Recommended Next Experiments" in report


def test_render_report_includes_benchmark_results(tmp_path):
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=2,
        out_dir=tmp_path / "run",
        benchmark_results=[
            BenchmarkResult(
                id="bench-1",
                name="Seeded benchmark",
                source="benchmark.json",
                baseline_metrics={"pass_rate": 0.5, "regression_count": 2.0},
                candidate_metrics={"pass_rate": 0.75, "regression_count": 1.0},
                deltas={"pass_rate": 0.25, "regression_count": -1.0},
                success=True,
                notes=["Local fixture"],
            )
        ],
    )

    report = render_report(state)

    assert "## Benchmark Results" in report
    assert "Seeded benchmark" in report
    assert "pass_rate: baseline 0.5, candidate 0.75, delta +0.25" in report
