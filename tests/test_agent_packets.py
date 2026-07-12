from code_scientist.agent_packets import select_top_hypotheses
from code_scientist.models import Hypothesis, RunState, TestPlan


def _hyp(hid: str, status: str, elo: float) -> Hypothesis:
    return Hypothesis(
        id=hid,
        title=f"Title {hid}",
        claim=f"Claim {hid}",
        rationale="rationale",
        assumptions=["a"],
        evidence_refs=[],
        test_plan=TestPlan(experiment="e", metrics=["m"], success_condition="s"),
        risks=["risk"],
        origin="test",
        elo=elo,
        status=status,
    )


def test_select_top_hypotheses_excludes_inactive_statuses():
    # A safety-quarantined or review-rejected hypothesis must never be selected
    # for a subagent work packet, even with a competitive Elo.
    state = RunState(
        goal=None,
        hypotheses=[
            _hyp("hyp-live", "candidate", 1300.0),
            _hyp("hyp-quarantined", "quarantined", 1400.0),
            _hyp("hyp-rejected", "rejected", 1350.0),
            _hyp("hyp-merged", "merged_duplicate", 1500.0),
            _hyp("hyp-second", "candidate", 1250.0),
        ],
    )

    selected = select_top_hypotheses(state, limit=5)
    selected_ids = {item.id for item in selected}

    assert selected_ids == {"hyp-live", "hyp-second"}
    assert "hyp-quarantined" not in selected_ids
    assert "hyp-rejected" not in selected_ids
    assert "hyp-merged" not in selected_ids
