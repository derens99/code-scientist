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
    assert restored.plan is not None
    assert restored.hypotheses
    assert restored.reviews
    assert restored.matches
    assert restored.proximity_edges
    assert restored.meta_reviews
    assert restored.context_snapshots
    assert restored.context_snapshots[-1].scheduler_weights["ranking"] >= 1.0


def test_supervisor_can_run_with_injected_anthropic_client(tmp_path):
    class FakeLLM:
        def complete(self, prompt, max_tokens):
            return json.dumps(
                [
                    {
                        "title": "Repo-aware idea search",
                        "claim": "Using repository traces to seed idea search will improve LLM coding-agent eval pass rate.",
                        "rationale": "Repo traces make ideas more concrete and testable.",
                        "assumptions": ["Trace data is available."],
                        "risks": ["overfitting to one repository"],
                    }
                ]
            )

    out_dir = tmp_path / "run"

    state = run_research_cycle(
        objective="Find testable ideas to improve LLM coding agents",
        cycles=1,
        max_hypotheses=3,
        max_matches=1,
        out_dir=out_dir,
        provider="anthropic",
        llm_client=FakeLLM(),
    )

    assert state.hypotheses
    assert any(item.origin == "anthropic-haiku" for item in state.hypotheses)
