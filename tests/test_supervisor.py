import json

from code_scientist.models import RunState
from code_scientist.supervisor import run_research_cycle


def test_supervisor_writes_state(tmp_path):
    out_dir = tmp_path / "run"
    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=4,
        max_matches=2,
        out_dir=out_dir,
    )

    state_path = out_dir / "state.json"
    assert state_path.exists()
    restored = RunState.from_dict(json.loads(state_path.read_text()))
    assert restored.goal.objective == state.goal.objective
    assert restored.hypotheses
    assert restored.reviews
    assert restored.matches
    assert restored.meta_reviews
