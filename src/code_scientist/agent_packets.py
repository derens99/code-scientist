from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from code_scientist.models import Evidence, Hypothesis, Review, RunState


def write_agent_packets(
    state: RunState,
    *,
    state_path: str | Path,
    out_dir: str | Path,
    limit: int = 3,
) -> dict[str, Any]:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    selected = _select_hypotheses(state, limit=limit)
    packets = []
    for hypothesis in selected:
        packet_path = output / f"{_safe_filename(hypothesis.id)}.md"
        reviews = [review for review in state.reviews if review.hypothesis_id == hypothesis.id]
        evidence = _evidence_for_hypothesis(state.evidence, hypothesis, reviews)
        packet_path.write_text(
            render_agent_packet(
                state,
                hypothesis,
                reviews=reviews,
                evidence=evidence,
                state_path=state_path,
            ),
            encoding="utf-8",
        )
        packets.append(
            {
                "hypothesis_id": hypothesis.id,
                "title": hypothesis.title,
                "elo": hypothesis.elo,
                "status": hypothesis.status,
                "path": packet_path.name,
                "review_ids": [review.id for review in reviews],
                "evidence_refs": sorted({item.id for item in evidence}),
            }
        )
    index = {
        "objective": state.goal.objective,
        "state_path": str(state_path),
        "packet_count": len(packets),
        "packets": packets,
    }
    (output / "packet-index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def render_agent_packet(
    state: RunState,
    hypothesis: Hypothesis,
    *,
    reviews: list[Review],
    evidence: list[Evidence],
    state_path: str | Path,
) -> str:
    lines = [
        f"# Code Scientist Agent Packet: {hypothesis.title}",
        "",
        "Spawn a subagent for this Code Scientist packet.",
        "",
        "## Assignment",
        "",
        "- Review the hypothesis as an independent coding-agent research reviewer.",
        "- Identify the strongest implementation or evaluation next step.",
        "- Check whether the evidence and reviews support the claim.",
        "- Return concise findings, risks, and recommended follow-up work.",
        "- Do not edit source files unless the parent agent explicitly asks for implementation.",
        "",
        "## Run Context",
        "",
        f"- Objective: {state.goal.objective}",
        f"- State file: {state_path}",
        f"- Run status: {state.run_status}",
        "",
        "## Hypothesis",
        "",
        f"- Id: {hypothesis.id}",
        f"- Status: {hypothesis.status}",
        f"- Elo: {hypothesis.elo:.1f}",
        f"- Claim: {hypothesis.claim}",
        f"- Rationale: {hypothesis.rationale}",
        f"- Origin: {hypothesis.origin}",
        "",
        "### Assumptions",
        "",
    ]
    lines.extend(_bullet_lines(hypothesis.assumptions))
    lines.extend(
        [
            "",
            "### Test Plan",
            "",
            f"- Experiment: {hypothesis.test_plan.experiment}",
            f"- Metrics: {', '.join(hypothesis.test_plan.metrics) or 'none'}",
            f"- Success condition: {hypothesis.test_plan.success_condition}",
            "",
            "### Risks",
            "",
        ]
    )
    lines.extend(_bullet_lines(hypothesis.risks))
    lines.extend(["", "## Reviews", ""])
    if reviews:
        for review in reviews:
            lines.extend(
                [
                    f"- {review.id}: {review.review_type}; decision={review.decision}; "
                    f"confidence={review.confidence:.2f}",
                    f"  - Scores: {_format_scores(review.scores)}",
                ]
            )
            if review.strengths:
                lines.append(f"  - Strengths: {'; '.join(review.strengths)}")
            if review.weaknesses:
                lines.append(f"  - Weaknesses: {'; '.join(review.weaknesses)}")
            if review.findings:
                lines.append(f"  - Findings: {'; '.join(review.findings)}")
            if review.safety_notes:
                lines.append(f"  - Safety notes: {'; '.join(review.safety_notes)}")
            if review.evidence_refs:
                lines.append(f"  - Evidence refs: {', '.join(review.evidence_refs)}")
    else:
        lines.append("- No reviews recorded for this hypothesis.")
    lines.extend(["", "## Evidence References", ""])
    if evidence:
        for item in evidence:
            preview = " ".join(item.content.split())[:280]
            lines.append(f"- {item.id}: {item.kind}; source={item.source}")
            lines.append(f"  - {preview}")
    else:
        lines.append("- No evidence records resolved for this packet.")
    if state.research_overview:
        lines.extend(
            [
                "",
                "## Research Overview",
                "",
                f"- Summary: {state.research_overview.summary}",
                f"- Promising directions: {', '.join(state.research_overview.promising_directions) or 'none'}",
                "",
                "### Next Experiments",
                "",
            ]
        )
        lines.extend(_bullet_lines(state.research_overview.next_experiments))
        lines.extend(["", "### Limitations", ""])
        lines.extend(_bullet_lines(state.research_overview.limitations))
    lines.extend(
        [
            "",
            "## Response Format",
            "",
            "- Verdict: keep, revise, verify, or reject.",
            "- Key evidence: cite hypothesis, review, and evidence ids.",
            "- Main risk: the biggest failure mode or missing proof.",
            "- Next action: one concrete implementation, benchmark, or review step.",
        ]
    )
    return "\n".join(lines) + "\n"


def _select_hypotheses(state: RunState, *, limit: int) -> list[Hypothesis]:
    active = [item for item in state.hypotheses if item.status != "merged_duplicate"]
    if not active or limit <= 0:
        return []
    overview_order = {
        hypothesis_id: index
        for index, hypothesis_id in enumerate(
            state.research_overview.top_hypothesis_ids if state.research_overview else []
        )
    }
    return sorted(
        active,
        key=lambda item: (
            overview_order.get(item.id, len(overview_order)),
            -item.elo,
            item.id,
        ),
    )[:limit]


def _evidence_for_hypothesis(
    evidence: list[Evidence],
    hypothesis: Hypothesis,
    reviews: list[Review],
) -> list[Evidence]:
    wanted = set(hypothesis.evidence_refs)
    for review in reviews:
        wanted.update(review.evidence_refs)
    by_id = {item.id: item for item in evidence}
    return [by_id[item_id] for item_id in sorted(wanted) if item_id in by_id]


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return cleaned or "packet"


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None recorded."]


def _format_scores(scores: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(scores.items())) or "none"
