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
        "## Research Plan Configuration",
        "",
    ]
    if state.plan:
        lines.extend(
            [
                f"- Plan id: {state.plan.id}",
                f"- Evaluation criteria: {', '.join(state.plan.evaluation_criteria)}",
                f"- Generation methods: {', '.join(state.plan.generation_methods)}",
                f"- Review types: {', '.join(state.plan.review_types)}",
                f"- Evolution strategies: {', '.join(state.plan.evolution_strategies)}",
                f"- Scheduler weights: {_format_weights(state.plan.scheduler_weights)}",
                "",
            ]
        )
    else:
        lines.extend(["- No research plan configuration recorded.", ""])

    lines.extend(["## Context Memory", ""])
    if state.context_snapshots:
        latest = state.context_snapshots[-1]
        lines.extend(
            [
                f"- Latest cycle: {latest.cycle}",
                f"- Accepted hypotheses: {latest.accepted_total}",
                f"- Reviews: {latest.review_total}",
                f"- Tournament matches: {latest.match_total}",
                f"- Proximity edges: {latest.proximity_edge_count}",
                f"- Scheduler weights: {_format_weights(latest.scheduler_weights)}",
                f"- Next actions: {', '.join(latest.next_actions)}",
                "",
            ]
        )
    else:
        lines.extend(["- No context snapshots recorded.", ""])

    lines.extend(["## Proximity Graph", ""])
    if state.proximity_edges:
        for edge in state.proximity_edges[:5]:
            lines.append(f"- {edge.source} <-> {edge.target}: similarity {edge.similarity:.3f}")
        lines.append("")
    else:
        lines.extend(["- No proximity edges recorded.", ""])

    lines.extend(["## Benchmark Results", ""])
    if state.benchmark_results:
        for result in state.benchmark_results:
            lines.append(f"- {result.name}: {'passed' if result.success else 'needs review'}")
            lines.append(f"  - Source: {result.source}")
            for metric in sorted(result.candidate_metrics):
                baseline = result.baseline_metrics[metric]
                candidate = result.candidate_metrics[metric]
                delta = result.deltas[metric]
                lines.append(
                    f"  - {metric}: baseline {baseline:g}, candidate {candidate:g}, "
                    f"delta {_format_delta(delta)}"
                )
            if result.notes:
                lines.append(f"  - Notes: {', '.join(result.notes)}")
        lines.append("")
    else:
        lines.extend(["- No benchmark results recorded.", ""])

    lines.extend(
        [
            "## Ranked Hypotheses",
            "",
        ]
    )
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


def _format_weights(weights: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:g}" for name, value in sorted(weights.items()))


def _format_delta(value: float) -> str:
    return f"{value:+g}"
