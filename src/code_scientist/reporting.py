from __future__ import annotations

from code_scientist.models import RunState


def render_report(state: RunState) -> str:
    lines: list[str] = [
        "# Code Scientist Research Report",
        "",
        f"Objective: {state.goal.objective}",
        "",
        "## Safety Status",
        "",
        f"- Allowed: {state.safety.allowed if state.safety else True}",
        f"- Reason: {state.safety.reason if state.safety else 'No safety decision recorded.'}",
        "",
        "## Method Summary",
        "",
        "This run generated, reviewed, ranked, evolved, and meta-reviewed AI/LLM/code improvement hypotheses.",
        "Elo is an auto-evaluation proxy, not ground truth.",
        "",
        "## Ranked Hypotheses",
        "",
    ]
    for index, hypothesis in enumerate(state.hypotheses, start=1):
        lines.extend(
            [
                f"{index}. {hypothesis.title} - Elo {hypothesis.elo:.1f}",
                f"   - Claim: {hypothesis.claim}",
                f"   - Test: {hypothesis.test_plan.experiment}",
                f"   - Metrics: {', '.join(hypothesis.test_plan.metrics)}",
            ]
        )

    lines.extend(["", "## Reviews And Critiques", ""])
    for review in state.reviews:
        lines.append(f"- {review.hypothesis_id}: {review.decision}; weaknesses: {', '.join(review.weaknesses)}")

    lines.extend(["", "## Evolution Lineage", ""])
    children = [item for item in state.hypotheses if item.parent_ids]
    if children:
        for child in children:
            lines.append(f"- {child.id} derives from {', '.join(child.parent_ids)}")
    else:
        lines.append("- No evolved hypotheses were accepted in this run.")

    lines.extend(["", "## Meta-Review", ""])
    for meta in state.meta_reviews:
        lines.append(f"- Common weaknesses: {', '.join(meta.common_weaknesses)}")
        lines.append(f"- Prompt feedback: {', '.join(meta.prompt_feedback)}")

    lines.extend(["", "## Recommended Next Experiments", ""])
    for hypothesis in state.hypotheses[:3]:
        lines.append(f"- Test `{hypothesis.title}` with metrics: {', '.join(hypothesis.test_plan.metrics)}")

    lines.extend(
        [
            "",
            "## Limitations And Uncertainty",
            "",
            "- Generated hypotheses are research candidates, not verified improvements.",
            "- Elo rankings are internal preference signals and require benchmark validation.",
            "- Reports must not be used as evidence of model improvement without measured deltas.",
            "",
        ]
    )
    return "\n".join(lines)
