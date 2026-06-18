from code_scientist.elo import update_elo
from code_scientist.models import Hypothesis, TestPlan
from code_scientist.safety import review_goal_safety, review_hypothesis_safety


def _hypothesis(claim: str) -> Hypothesis:
    return Hypothesis(
        id="hyp-x",
        title="Example",
        claim=claim,
        rationale="A concrete rationale.",
        assumptions=["A testable assumption."],
        evidence_refs=["ev-1"],
        test_plan=TestPlan(
            experiment="Compare baseline and candidate.",
            metrics=["pass_rate"],
            success_condition="Candidate improves pass rate.",
        ),
        risks=["Possible cost increase"],
        origin="test",
    )


def test_goal_safety_blocks_uncontrolled_self_modification():
    decision = review_goal_safety("Let the model secretly rewrite and deploy itself")

    assert decision.allowed is False
    assert "self-modification" in decision.flags


def test_hypothesis_safety_requires_audit_boundary():
    decision = review_hypothesis_safety(_hypothesis("Autonomously deploy patches without review"))

    assert decision.allowed is False
    assert "unreviewed-deployment" in decision.flags


def test_update_elo_moves_winner_up_and_loser_down():
    winner, loser = update_elo(1200.0, 1200.0)

    assert winner > 1200.0
    assert loser < 1200.0
