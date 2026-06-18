from code_scientist.reporting import render_report
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
    assert "Ranked Hypotheses" in report
    assert "Elo is an auto-evaluation proxy" in report
    assert "Recommended Next Experiments" in report
