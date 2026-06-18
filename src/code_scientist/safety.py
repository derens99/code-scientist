from __future__ import annotations

from code_scientist.models import Hypothesis, SafetyDecision


SELF_MODIFICATION_TERMS = ("rewrite itself", "modify itself", "self-modify", "self modification")
SECRET_TERMS = ("secretly", "hide", "without logging", "covert")
DEPLOY_TERMS = ("deploy", "production", "release")
NO_REVIEW_TERMS = ("without review", "without human", "unreviewed")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def review_goal_safety(objective: str) -> SafetyDecision:
    flags: list[str] = []
    lowered = objective.lower()
    if _contains_any(objective, SELF_MODIFICATION_TERMS) or ("rewrite" in lowered and "itself" in lowered):
        flags.append("self-modification")
    if _contains_any(objective, SECRET_TERMS):
        flags.append("hidden-execution")
    if _contains_any(objective, DEPLOY_TERMS) and _contains_any(objective, NO_REVIEW_TERMS):
        flags.append("unreviewed-deployment")
    if flags:
        return SafetyDecision(False, "Objective requests unsafe autonomous behavior.", flags)
    return SafetyDecision(True, "Objective is allowed for local research planning.", [])


def review_hypothesis_safety(hypothesis: Hypothesis) -> SafetyDecision:
    text = " ".join([hypothesis.title, hypothesis.claim, hypothesis.rationale, *hypothesis.risks])
    flags: list[str] = []
    if _contains_any(text, SELF_MODIFICATION_TERMS):
        flags.append("self-modification")
    if _contains_any(text, DEPLOY_TERMS) and _contains_any(text, NO_REVIEW_TERMS):
        flags.append("unreviewed-deployment")
    if _contains_any(text, SECRET_TERMS):
        flags.append("hidden-execution")
    if flags:
        return SafetyDecision(False, "Hypothesis violates local research safety boundaries.", flags)
    return SafetyDecision(True, "Hypothesis stays within local research boundaries.", [])
