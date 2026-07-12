from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from code_scientist.agent_packets import select_top_hypotheses
from code_scientist.benchmarks import summarize_benchmark_comparison_study
from code_scientist.evidence import EvidenceStore
from code_scientist.evaluation import (
    audit_capability_study_coverage,
    summarize_capability_study,
    summarize_capability_study_from_states,
)
from code_scientist.models import BenchmarkResult, Evidence, ProximityEdge, RunState
from code_scientist.safety import (
    _SAFETY_REVIEW_TYPES,
    _safety_rejected_hypothesis_ids,
)


_CITATION_RELEVANCE_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "any",
    "are",
    "before",
    "being",
    "but",
    "can",
    "cited",
    "citation",
    "could",
    "does",
    "evidence",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "may",
    "must",
    "not",
    "notes",
    "only",
    "record",
    "records",
    "should",
    "that",
    "the",
    "their",
    "this",
    "through",
    "use",
    "used",
    "using",
    "with",
}


def render_benchmark_comparison_study_report(
    results: list[BenchmarkResult],
    summary: dict[str, float | int] | None = None,
) -> str:
    study_summary = summary or summarize_benchmark_comparison_study(results)
    lines = [
        "# Code Scientist Benchmark Comparison Study",
        "",
        f"- Comparisons: {study_summary['comparison_count']}",
        f"- Successful comparisons: {study_summary['success_count']}",
        f"- Success rate: {study_summary['success_rate']:.3f}",
        f"- Mean pass-rate delta: {_format_delta(float(study_summary['mean_pass_rate_delta']))}",
        f"- Total regression delta: {_format_delta(float(study_summary['total_regression_delta']))}",
        f"- Mean tool-call delta: {_format_delta(float(study_summary['mean_tool_calls_delta']))}",
        f"- Mean wall-time delta: {_format_delta(float(study_summary['mean_wall_time_delta']))}",
        f"- Mean cost delta: {_format_delta(float(study_summary['mean_cost_delta']))}",
        "",
        "## Comparison Results",
        "",
    ]
    if not results:
        lines.append("- No benchmark comparisons were included.")
        lines.append("")
        return "\n".join(lines)

    for result in results:
        lines.append(f"- {result.name}: {'success' if result.success else 'regression'}")
        lines.append(f"  - Source: {result.source}")
        lines.append(f"  - Pass-rate delta: {_format_delta(result.deltas.get('pass_rate', 0.0))}")
        lines.append(f"  - Regression delta: {_format_delta(result.deltas.get('regression_count', 0.0))}")
        lines.append(f"  - Tool-call delta: {_format_delta(result.deltas.get('tool_calls', 0.0))}")
        lines.append(f"  - Wall-time delta: {_format_delta(result.deltas.get('wall_time', 0.0))}")
        lines.append(f"  - Cost delta: {_format_delta(result.deltas.get('cost', 0.0))}")
        if result.notes:
            lines.append(f"  - Notes: {'; '.join(result.notes[:3])}")
    lines.append("")
    return "\n".join(lines)


def render_capability_study_report(states: list[RunState]) -> str:
    summary = summarize_capability_study_from_states(states)
    coverage = audit_capability_study_coverage(states)
    lines = [
        "# Code Scientist Capability Study",
        "",
        f"- Runs: {len(states)}",
        f"- Baseline evaluations: {summary.evaluation_count}",
        f"- Baseline win rate: {summary.baseline_win_rate:.3f}",
        f"- Mean score delta: {_format_delta(summary.mean_score_delta)}",
        f"- Score delta sample count: {summary.score_delta_count}",
        f"- Score delta 95% CI: [{_format_delta(summary.score_delta_ci_low)}, "
        f"{_format_delta(summary.score_delta_ci_high)}]",
        f"- Score delta effect size: {summary.score_delta_effect_size:.3f}",
        f"- Baseline win sign-test p-value: {summary.baseline_win_sign_test_p_value:.3f}",
        f"- Mean Elo-human correlation: {summary.mean_elo_human_correlation:.3f}",
        f"- Mean Elo-benchmark correlation: {summary.mean_elo_benchmark_correlation:.3f}",
        f"- Scaling points: {summary.scaling_point_count}",
        f"- Scaling delta trend: {_format_delta(summary.scaling_delta_trend)}",
        f"- Prospective records: {summary.prospective_count}",
        f"- Prospective success rate: {summary.prospective_success_rate:.3f}",
        f"- Feedback-loop measurements: {summary.feedback_loop_measurement_count}",
        f"- Feedback-loop positive rate: {summary.feedback_loop_positive_rate:.3f}",
        f"- Feedback-loop mean delta: {_format_delta(summary.feedback_loop_mean_delta)}",
        f"- Feedback-loop metric deltas: {_format_metric_deltas(summary.feedback_loop_metric_deltas) or 'none'}",
        f"- Summary: {summary.summary}",
        "",
        "## Study Coverage Audit",
        "",
        f"- Status: {'complete' if coverage.passed else 'incomplete'}",
        f"- Unique goals: {coverage.unique_goal_count}",
        f"- Baselines: {', '.join(coverage.baseline_names) or 'none'}",
        f"- Capability evaluations: {coverage.capability_evaluation_count}",
        f"- Human-scored candidates: {coverage.human_scored_candidate_count}",
        f"- Human rubric judgments: {coverage.human_rubric_judgment_count}",
        f"- Human preference judgments: {coverage.human_preference_judgment_count}",
        f"- Benchmark-scored candidates: {coverage.benchmark_scored_candidate_count}",
        f"- Benchmark result artifacts: {coverage.benchmark_result_count}",
        f"- Scaling points: {coverage.scaling_point_count}",
        f"- Prospective/external measurements: {coverage.measured_prospective_count}",
        f"- Feedback-loop measurements: {coverage.measured_feedback_loop_count}",
        f"- Safety evaluations: {coverage.safety_evaluation_count}",
        f"- Elo concordance results: {coverage.elo_concordance_count}",
        f"- Elo trajectory points: {coverage.elo_trajectory_point_count}",
        f"- Missing requirements: {', '.join(coverage.missing_requirements) or 'none'}",
        f"- Summary: {coverage.summary}",
        "",
    ]
    if states:
        lines.extend(["## Included Goals", ""])
        for state in states:
            lines.append(f"- {state.goal.objective}")
        lines.append("")
    ablation_rows = _component_ablation_rows(states)
    proximity_correlations = [
        value
        for state in states
        if (value := _proximity_quality_difference_correlation(state)) is not None
    ]
    lines.extend(["## Component Ablation Readout", ""])
    if ablation_rows:
        for component, baseline_label, candidate_label, baseline_score, candidate_score in ablation_rows:
            lines.append(
                f"- {component}: {baseline_label} {baseline_score:.3f}; "
                f"{candidate_label} {candidate_score:.3f}; "
                f"delta {_format_delta(candidate_score - baseline_score)}"
            )
    else:
        lines.append("- No complete paired ablation arms found.")
    if proximity_correlations:
        lines.append(
            "- Proximity-vs-review-quality-difference correlation: "
            f"{sum(proximity_correlations) / len(proximity_correlations):.3f} "
            f"across {len(proximity_correlations)} runs"
        )
        lines.append(
            "  - This is a review-score proxy; replace it with independent expert quality scores "
            "for a paper-level result."
        )
    else:
        lines.append("- Proximity-vs-quality-difference correlation: not measurable from these runs.")
    lines.append("")
    return "\n".join(lines)


def _component_ablation_rows(
    states: list[RunState],
) -> list[tuple[str, str, str, float, float]]:
    score_by_label = {
        point.label: point.code_scientist_score
        for state in states
        for point in state.scaling_curve
        if point.label
    }
    pairs = [
        ("generation strategy", "generation-paper-seeded", "generation-assumption"),
        ("reflection search", "reflection-search-off", "reflection-search-on"),
        ("ranking debate", "ranking-simple", "ranking-debate"),
        ("evolution", "evolution-off", "evolution-on"),
        ("review depth", "review-recurrent", "review-full"),
        ("proximity", "proximity-off", "proximity-on"),
    ]
    return [
        (component, baseline, candidate, score_by_label[baseline], score_by_label[candidate])
        for component, baseline, candidate in pairs
        if baseline in score_by_label and candidate in score_by_label
    ]


def _proximity_quality_difference_correlation(state: RunState) -> float | None:
    score_values: dict[str, list[float]] = {}
    for review in state.reviews:
        if not review.scores:
            continue
        score_values.setdefault(review.hypothesis_id, []).append(
            sum(review.scores.values()) / len(review.scores)
        )
    quality = {
        hypothesis_id: sum(values) / len(values)
        for hypothesis_id, values in score_values.items()
        if values
    }
    pairs = [
        (edge.similarity, abs(quality[edge.source] - quality[edge.target]))
        for edge in state.proximity_edges
        if edge.source in quality and edge.target in quality
    ]
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    denominator_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if denominator_x == 0 or denominator_y == 0:
        return None
    return round(numerator / (denominator_x * denominator_y), 3)


def render_findings(
    state: RunState,
    *,
    limit: int = 5,
    packet_review_notes: dict[str, str] | None = None,
) -> str:
    """Render a concise, decision-oriented digest of a run.

    Unlike render_report, which records everything, this lists only the ranked
    findings with their review outcomes, what was rejected and why, the
    recommended next experiments, and the independent packet-reviewer verdicts
    when the host saved them under agent-packets/reviews/.
    """

    notes = packet_review_notes or {}
    measured_by_hypothesis = {
        result.hypothesis_id: result
        for result in state.benchmark_results
        if result.hypothesis_id and result.provenance.startswith("measured")
    }
    reviews_by_hypothesis: dict[str, list] = {}
    for review in state.reviews:
        reviews_by_hypothesis.setdefault(review.hypothesis_id, []).append(review)
    rejected_ids = {
        review.hypothesis_id for review in state.reviews if review.decision == "reject"
    }
    ranked_pool = select_top_hypotheses(state, limit=max(len(state.hypotheses), 1))
    ranked = [item for item in ranked_pool if item.id not in rejected_ids][: max(int(limit), 1)]

    lines: list[str] = [f"# Research Findings: {state.goal.objective}", ""]
    origins = sorted({item.origin for item in state.hypotheses})
    lines.append(
        f"Run status: {state.run_status} | hypotheses: {len(state.hypotheses)} | "
        f"reviews: {len(state.reviews)} | matches: {len(state.matches)} | "
        f"evidence: {len(state.evidence)}"
    )
    if origins:
        lines.append(f"Hypothesis origins: {', '.join(origins)}")
    lines.extend(["", "## Top Findings", ""])
    if not ranked:
        lines.extend(["- No hypotheses were produced.", ""])
    for position, hypothesis in enumerate(ranked, start=1):
        hypothesis_reviews = reviews_by_hypothesis.get(hypothesis.id, [])
        strengths = _unique_ordered(
            [item for review in hypothesis_reviews for item in review.strengths]
        )[:2]
        weaknesses = _unique_ordered(
            [item for review in hypothesis_reviews for item in review.weaknesses]
        )[:2]
        experiment = next(
            (item for review in hypothesis_reviews for item in review.findings),
            "",
        ) or hypothesis.test_plan.experiment
        lines.append(f"### {position}. {hypothesis.title}")
        lines.append("")
        lines.append(hypothesis.claim)
        lines.append("")
        lines.append(
            f"- Id: {hypothesis.id} | Status: {hypothesis.status} | "
            f"Elo: {hypothesis.elo:.1f} | Origin: {hypothesis.origin}"
        )
        if strengths:
            lines.append(f"- Why it matters: {'; '.join(strengths)}")
        if weaknesses:
            lines.append(f"- Open risks: {'; '.join(weaknesses)}")
        if experiment:
            lines.append(f"- Suggested experiment: {_single_line(experiment)}")
        note = notes.get(hypothesis.id, "")
        if note:
            verdict = _reviewer_verdict(note) or "recorded"
            lines.append(
                f"- Independent reviewer verdict: {verdict} "
                f"(agent-packets/reviews/{hypothesis.id}.md)"
            )
        else:
            lines.append("- Independent reviewer verdict: not yet reviewed")
        measured = measured_by_hypothesis.get(hypothesis.id)
        if measured:
            delta = measured.stats.get("pass_rate_delta", measured.deltas.get("pass_rate", 0.0))
            p_value = measured.stats.get("mcnemar_p_one_sided")
            detail = f"pass-rate delta {delta:+.3f}"
            if p_value is not None:
                detail += f", one-sided McNemar p={p_value:.4f}"
            lines.append(
                f"- Measured result: **{measured.verdict or 'recorded'}** ({detail}; {measured.source})"
            )
        lines.append("")

    rejected_lines: list[str] = []
    for hypothesis in state.hypotheses:
        if hypothesis.id not in rejected_ids:
            continue
        reject_reviews = [
            review
            for review in reviews_by_hypothesis.get(hypothesis.id, [])
            if review.decision == "reject"
        ]
        reason = next(
            (item for review in reject_reviews for item in review.weaknesses),
            "rejected in review",
        )
        rejected_lines.append(f"- {hypothesis.title} ({hypothesis.id}): {_single_line(reason)}")
    if rejected_lines:
        lines.extend(["## Rejected In Review", "", *rejected_lines, ""])

    overview = state.research_overview
    latest_meta = state.meta_reviews[-1] if state.meta_reviews else None
    next_experiments = (overview.next_experiments if overview else []) or (
        latest_meta.promising_directions if latest_meta else []
    )
    if next_experiments:
        lines.extend(
            ["## Recommended Next Experiments", "", *[f"- {item}" for item in next_experiments], ""]
        )
    if latest_meta and latest_meta.missing_evidence:
        lines.extend(
            ["## Missing Evidence", "", *[f"- {item}" for item in latest_meta.missing_evidence], ""]
        )

    limitations = list(overview.limitations) if overview else []
    if not any(
        "proxy" in item.lower() or "auto-evaluation" in item.lower() for item in limitations
    ):
        limitations.append(
            "Elo rankings are auto-evaluation proxies; findings are candidate hypotheses, "
            "not validated improvements."
        )
    if measured_by_hypothesis:
        limitations.append(
            "Hypotheses marked with a measured result carry executed-experiment evidence "
            "scoped to that experiment's task suite and model; all other findings remain "
            "unvalidated candidates."
        )
    lines.extend(["## Limitations", "", *[f"- {item}" for item in limitations], ""])
    lines.extend(
        [
            "## Artifacts",
            "",
            "- state.json — full run state",
            "- report.md — comprehensive run report",
            "- agent-packets/ — bounded subagent review packets",
            "- agent-packets/reviews/ — independent packet-reviewer verdicts",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def load_packet_review_notes(directory: str | Path) -> dict[str, str]:
    """Load host-saved packet-reviewer notes keyed by hypothesis id.

    The /code-scientist skills save each reviewer's verdict as
    agent-packets/reviews/<hypothesis-id>.md after consolidation.
    """

    notes_dir = Path(directory)
    if not notes_dir.is_dir():
        return {}
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(notes_dir.glob("*.md"))
    }


def _reviewer_verdict(note: str) -> str:
    match = re.search(
        r"verdict[:*\s]+[*_`\s]*(keep|revise|verify|reject)",
        note,
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else ""


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


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
        "## Run Status",
        "",
        f"- Status: {state.run_status}",
        "- Append-only activity ledger: activity.jsonl",
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

    lines.extend(["## Goal Revision History", ""])
    if state.goal_revisions:
        for revision in state.goal_revisions:
            lines.append(
                f"- Revision {revision.revision}: {revision.approval_status}; "
                f"{revision.prior_goal_id} -> {revision.new_goal_id}"
            )
            lines.append(f"  - Safety allowed: {revision.safety.allowed}")
            lines.append(f"  - Safety reason: {revision.safety.reason}")
            if revision.user_message:
                lines.append(f"  - User message: {_single_line(revision.user_message)}")
            if revision.structured_changes:
                lines.append(
                    "  - Changed fields: "
                    + ", ".join(sorted(revision.structured_changes))
                )
            lines.append(
                f"  - Superseded queued/deferred tasks: {len(revision.affected_task_ids)}"
            )
        lines.append("")
    else:
        lines.extend(["- No in-run goal revisions recorded.", ""])

    lines.extend(["## Research Overview", ""])
    if state.research_overview:
        overview = state.research_overview
        lines.extend(
            [
                f"- Summary: {overview.summary}",
                f"- Generated by: {overview.generated_by}",
                f"- Top hypotheses: {', '.join(overview.top_hypothesis_ids) or 'None recorded.'}",
                f"- Promising directions: {', '.join(overview.promising_directions) or 'None recorded.'}",
                "",
                "### Overview Next Experiments",
                "",
            ]
        )
        for experiment in overview.next_experiments:
            lines.append(f"- {experiment}")
        lines.extend(["", "### Overview Limitations", ""])
        for limitation in overview.limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    else:
        lines.extend(["- No first-class research overview recorded.", ""])

    lines.extend(["## Research Output Artifacts", ""])
    if state.research_output_artifacts:
        for artifact in state.research_output_artifacts:
            lines.append(f"- {artifact.output_type}: {artifact.title}")
            lines.append(f"  - Summary: {artifact.summary}")
            if artifact.related_hypothesis_ids:
                lines.append(f"  - Related hypotheses: {', '.join(artifact.related_hypothesis_ids)}")
            if artifact.evidence_refs:
                lines.append(f"  - Evidence refs: {', '.join(artifact.evidence_refs)}")
            if artifact.contact_targets:
                lines.append(f"  - Contact targets: {', '.join(artifact.contact_targets)}")
            for section, content in artifact.sections.items():
                lines.append(f"  - {section}: {content}")
        lines.append("")
    else:
        lines.extend(["- No publication, grant, or contact artifacts recorded.", ""])

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

    lines.extend(["## Retrieval Memory", ""])
    if state.retrieval_memory:
        agent_counts = Counter(record.agent or "unassigned" for record in state.retrieval_memory)
        lines.append(f"- Retrieval records: {len(state.retrieval_memory)}")
        lines.append(f"- Agent counts: {_format_counts(agent_counts)}")
        for record in state.retrieval_memory[-8:]:
            lines.append(
                f"- Cycle {record.cycle} {record.agent or 'unassigned'} {record.id}: "
                f"{record.retrieval_method}; task {record.task_id or 'none'}"
            )
            lines.append(f"  - Query: {_single_line(record.query)[:240]}")
            if record.reason:
                lines.append(f"  - Reason: {record.reason}")
            if record.evidence_refs:
                lines.append(f"  - Evidence refs: {', '.join(record.evidence_refs)}")
            if record.citations:
                lines.append(f"  - Citations: {'; '.join(record.citations[:3])}")
        lines.append("")
    else:
        lines.extend(["- No retrieval memory records persisted.", ""])

    lines.extend(["## Agent Tool Budget", ""])
    if state.tool_budget is not None:
        budget = state.tool_budget
        lines.append(f"- Limit: {budget.limit}")
        lines.append(f"- Used: {budget.used}")
        lines.append(f"- Remaining: {budget.remaining}")
        lines.append(f"- Exhausted: {'yes' if budget.exhausted else 'no'}")
        tool_counts = Counter(call.tool for call in state.agent_tool_calls)
        agent_counts = Counter(call.agent for call in state.agent_tool_calls)
        if tool_counts:
            lines.append(f"- Calls by tool: {_format_counts(tool_counts)}")
        if agent_counts:
            lines.append(f"- Calls by agent: {_format_counts(agent_counts)}")
        for call in state.agent_tool_calls[-8:]:
            lines.append(
                f"- Cycle {call.cycle} {call.agent} {call.tool}: {call.status}; "
                f"task {call.task_id or 'none'}; budget {call.budget_before}->{call.budget_after}"
            )
            lines.append(f"  - Query: {_single_line(call.query)[:240]}")
            if call.source_ref:
                lines.append(f"  - Source ref: {call.source_ref}")
            if call.rationale:
                lines.append(f"  - Rationale: {call.rationale}")
            if call.evidence_refs:
                lines.append(f"  - New evidence refs: {', '.join(call.evidence_refs)}")
            if call.blocked_reasons:
                lines.append(f"  - Blocked reasons: {', '.join(call.blocked_reasons)}")
            if call.error:
                lines.append(f"  - Error: {call.error}")
        lines.append("")
    else:
        lines.extend(["- Agent-driven retrieval is disabled for this run.", ""])

    lines.extend(["## Task Queue", ""])
    if state.task_queue:
        status_counts = Counter(task.status for task in state.task_queue)
        kind_counts = Counter(task.kind for task in state.task_queue)
        lines.append(f"- Status counts: {_format_counts(status_counts)}")
        lines.append(f"- Kind counts: {_format_counts(kind_counts)}")
        for task in state.task_queue[-8:]:
            lines.append(
                f"- {task.kind}: {task.status}; priority {task.priority:g}; "
                f"attempts {task.attempts}; results {', '.join(task.result_refs) or 'none'}"
            )
            if task.error:
                lines.append(f"  - Error: {task.error}")
            decision = task.worker_state.get("scheduler_decision")
            if isinstance(decision, dict):
                signals = [
                    str(signal)
                    for signal in decision.get("signals", [])
                    if isinstance(signal, str)
                ]
                lines.append(
                    "  - Scheduler decision: "
                    f"rank {decision.get('rank', 'n/a')}; "
                    f"score {decision.get('score', task.priority)}; "
                    f"candidates {decision.get('candidate_count', 'n/a')}; "
                    f"pool {decision.get('pool_size', 'n/a')}"
                )
                if signals:
                    lines.append(f"  - Scheduler signals: {', '.join(signals[:8])}")
        lines.append("")
    else:
        lines.extend(["- No task queue records persisted.", ""])

    lines.extend(["## Proximity Graph", ""])
    if state.proximity_edges:
        cluster_summaries = _proximity_cluster_summaries(state.proximity_edges)
        if cluster_summaries:
            lines.extend(["### Proximity Cluster Overview", ""])
            for summary in cluster_summaries:
                edge_label = "edge" if summary["edge_count"] == 1 else "edges"
                hypothesis_label = "hypothesis" if summary["hypothesis_count"] == 1 else "hypotheses"
                lines.append(
                    f"- {summary['cluster_id']}: {summary['edge_count']} {edge_label}; "
                    f"{summary['hypothesis_count']} {hypothesis_label}; "
                    f"top similarity {summary['top_similarity']:.3f}"
                )
                if summary["merge_count"] or summary["preserve_count"]:
                    lines.append(
                        f"  - Controls: merge {summary['merge_count']}; preserve {summary['preserve_count']}"
                    )
            lines.append("")

        lines.extend(["### Proximity Edges", ""])
        for edge in state.proximity_edges[:5]:
            lines.append(
                f"- {edge.source} <-> {edge.target}: similarity {edge.similarity:.3f}; "
                f"method {edge.method}; cluster {edge.cluster_id or 'unclustered'}"
            )
            if edge.reason:
                lines.append(f"  - Reason: {edge.reason}")
            if edge.deduplication_action:
                lines.append(f"  - Deduplication control: {edge.deduplication_action}")
            if edge.diversity_action:
                lines.append(f"  - Diversity control: {edge.diversity_action}")
            if edge.exploration_trace:
                lines.append("  - Proximity trace:")
                for trace_line in edge.exploration_trace:
                    lines.append(f"    - {trace_line}")
        lines.append("")
    else:
        lines.extend(["- No proximity edges recorded.", ""])

    lines.extend(["## Agent Trace Log", ""])
    if state.agent_traces:
        for trace in state.agent_traces[-10:]:
            lines.append(
                f"- Cycle {trace.cycle} {trace.agent}.{trace.action}: {trace.status}; "
                f"outputs {', '.join(trace.output_refs) or 'none'}"
            )
            if trace.task_id:
                lines.append(f"  - Task: {trace.task_id}")
            if trace.transcript_ref:
                lines.append(f"  - Transcript: {trace.transcript_ref}")
            if trace.notes:
                lines.append(f"  - Notes: {trace.notes}")
            if trace.evidence_refs:
                lines.append(f"  - Evidence: {', '.join(trace.evidence_refs)}")
            if trace.scratchpad:
                lines.append("  - Scratchpad:")
                for note in trace.scratchpad[:5]:
                    lines.append(f"    - {_single_line(note)[:240]}")
            if trace.tool_calls:
                lines.append(f"  - Tool calls: {len(trace.tool_calls)}")
                for tool_call in trace.tool_calls[:5]:
                    tool_name = _single_line(str(tool_call.get("tool_name", "tool")))
                    status = _single_line(str(tool_call.get("status", "unknown")))
                    lines.append(f"    - {tool_name}: {status}")
            if trace.llm_interactions:
                lines.append(f"  - LLM interactions: {len(trace.llm_interactions)}")
                for interaction in trace.llm_interactions[:3]:
                    turn = interaction.get("turn", "llm completion")
                    max_tokens = interaction.get("max_tokens", "")
                    prompt = _single_line(interaction.get("prompt", ""))[:240]
                    response = _single_line(interaction.get("response", ""))[:240]
                    lines.append(f"    - {turn}; max tokens {max_tokens or 'unknown'}")
                    if prompt:
                        lines.append(f"      - Prompt: {prompt}")
                    if response:
                        lines.append(f"      - Response: {response}")
        lines.append("")
    else:
        lines.extend(["- No agent traces recorded.", ""])

    lines.extend(["## Retrieved Evidence Coverage", ""])
    evidence_by_id = {item.id: item for item in state.evidence}
    evidence_kind_counts = Counter(item.kind for item in state.evidence)
    parser_counts = Counter(
        item.metadata.get("parser", "unspecified") for item in state.evidence
    )
    lines.append(f"- Evidence records: {len(state.evidence)}")
    lines.append(f"- Evidence kinds: {_format_counts(evidence_kind_counts)}")
    lines.append(f"- Parsers: {_format_counts(parser_counts)}")
    visual_claims = [item for item in state.evidence if item.kind == "pdf_visual_claim"]
    lines.append(f"- Machine-interpreted PDF visual claims: {len(visual_claims)}")
    for claim in visual_claims[:8]:
        lines.append(
            f"  - {claim.id}: page {claim.metadata.get('page_number', 'unknown')}; "
            f"model {claim.metadata.get('model', 'unknown')}; "
            f"confidence {claim.metadata.get('confidence', 'unknown')}; "
            f"parent {claim.metadata.get('parent_evidence_id', 'unknown')}"
        )
        lines.append(
            "    - Human verification required: "
            f"{claim.metadata.get('requires_human_verification', 'true')}"
        )
    validation_evidence = [
        item for item in state.evidence if item.kind == "agent_empirical_validation"
    ]
    lines.append(f"- Agent empirical validation records: {len(validation_evidence)}")
    for record in validation_evidence[:8]:
        lines.append(
            f"  - {record.id}: policy {record.metadata.get('execution_policy', 'unknown')}; "
            f"isolation {record.metadata.get('isolation_level', 'unknown')}; "
            f"network isolated {record.metadata.get('network_isolated', 'unknown')}; "
            f"ambient secrets inherited {record.metadata.get('ambient_secrets_inherited', 'unknown')}"
        )
    used_refs = _used_evidence_refs(state)
    if used_refs:
        for ref in used_refs[:12]:
            evidence = evidence_by_id.get(ref)
            if not evidence:
                lines.append(f"- {ref}: referenced but evidence record was not found in state.")
                continue
            lines.append(f"- {ref}: {evidence.kind} from {evidence.source}")
            lines.append(f"  - Notes: {evidence.notes}")
            citation = evidence.metadata.get("citation")
            if citation:
                lines.append(f"  - Citation: {citation}")
            lines.append(f"  - Content: {evidence.content[:240]}")
        lines.append("")
    else:
        lines.extend(["- No retrieved evidence citations recorded.", ""])

    citation_audit = _evidence_citation_audit(state, evidence_by_id)
    lines.extend(["## Evidence Citation Audit", ""])
    lines.append(f"- Referenced evidence ids: {len(citation_audit['referenced'])}")
    lines.append(f"- Resolved evidence ids: {len(citation_audit['resolved'])}")
    lines.append(f"- Unresolved evidence ids: {len(citation_audit['unresolved'])}")
    if citation_audit["unresolved"]:
        lines.append(f"- Missing references: {', '.join(citation_audit['unresolved'][:12])}")
    lines.append(f"- Uncited retrieved evidence records: {len(citation_audit['uncited'])}")
    if citation_audit["uncited"]:
        lines.append(f"- Uncited records: {', '.join(citation_audit['uncited'][:12])}")
    relevance_audit = _semantic_citation_relevance_audit(state, evidence_by_id)
    lines.extend(["", "### Semantic citation relevance audit", ""])
    lines.append(f"- Low-relevance resolved citations: {len(relevance_audit)}")
    for finding in relevance_audit[:12]:
        lines.append(f"- {finding}")
    lines.append("")

    lines.extend(["## Quarantined Hypotheses", ""])
    quarantined_hypotheses = [item for item in state.hypotheses if item.status == "quarantined"]
    if quarantined_hypotheses:
        safety_reject_ids = _safety_rejected_hypothesis_ids(state.reviews)
        safety_rejections = {
            review.hypothesis_id: review
            for review in state.reviews
            if review.hypothesis_id in safety_reject_ids
            and review.review_type in _SAFETY_REVIEW_TYPES
            and review.decision == "reject"
        }
        lines.append(
            "These hypotheses were rejected by safety review and are excluded from the tournament, "
            "evolution, and rankings. They are retained here for auditability only."
        )
        for hypothesis in quarantined_hypotheses:
            lines.append(f"- {hypothesis.id}: {hypothesis.title}")
            review = safety_rejections.get(hypothesis.id)
            if review is None:
                lines.append("  - Triggering review: not recorded in state.")
                continue
            lines.append(f"  - Triggering review decision: {review.decision} ({review.review_type})")
            lines.append(f"  - Flags: {', '.join(review.weaknesses) or 'none recorded'}")
            if review.safety_notes:
                lines.append(f"  - Reason: {review.safety_notes[0]}")
        lines.append("")
    else:
        lines.extend(["- No hypotheses were quarantined by safety review.", ""])

    lines.extend(["## Evidence Safety Review", ""])
    if state.evidence_safety_findings:
        rejected = [finding for finding in state.evidence_safety_findings if not finding.allowed]
        audited = [finding for finding in state.evidence_safety_findings if finding.allowed]
        lines.append(f"- Rejected evidence records: {len(rejected)}")
        for finding in rejected[:10]:
            lines.append(f"- {finding.source}: {', '.join(finding.flags) or 'flagged'}")
            lines.append(f"  - Reason: {finding.reason}")
            lines.append(f"  - Preview: {finding.content_preview}")
        lines.append(f"- Allowed evidence audit findings: {len(audited)}")
        for finding in audited[:10]:
            lines.append(f"- {finding.source}: {', '.join(finding.flags) or 'flagged'}")
            lines.append(f"  - Reason: {finding.reason}")
            lines.append(f"  - Preview: {finding.content_preview}")
        lines.append("")
    else:
        lines.extend(["- No unsafe retrieved evidence records rejected.", ""])

    lines.extend(["## Benchmark Results", ""])
    if state.benchmark_results:
        for result in state.benchmark_results:
            lines.append(f"- {result.name}: {'passed' if result.success else 'needs review'}")
            lines.append(f"  - Source: {result.source}")
            if result.provenance:
                origin = "executed experiment" if result.provenance.startswith("measured") else result.provenance
                lines.append(f"  - Provenance: {origin} ({result.provenance})")
            else:
                lines.append("  - Provenance: asserted fixture (metrics supplied, not executed by this engine)")
            if result.verdict:
                lines.append(f"  - Verdict: {result.verdict}")
            if result.hypothesis_id:
                lines.append(f"  - Hypothesis: {result.hypothesis_id}")
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

    lines.extend(["## Capability Evaluation", ""])
    if state.capability_evaluations:
        for evaluation in state.capability_evaluations:
            lines.append(
                f"- {evaluation.baseline_name}: baseline {evaluation.baseline_score:.3f}; "
                f"Code Scientist {evaluation.code_scientist_score:.3f}; "
                f"{'beats baseline' if evaluation.beats_baseline else 'does not beat baseline'}"
            )
            lines.append(f"  - Top hypothesis: {evaluation.top_hypothesis_id}")
            lines.append(f"  - Elo-human correlation: {evaluation.elo_human_correlation:.3f}")
            lines.append(f"  - Elo-benchmark correlation: {evaluation.elo_benchmark_correlation:.3f}")
            if evaluation.human_rubric_judgment_count:
                lines.append(f"  - Human rubric judgments: {evaluation.human_rubric_judgment_count}")
            if evaluation.human_rubric_criteria:
                lines.append(f"  - Rubric criteria: {', '.join(evaluation.human_rubric_criteria)}")
            if evaluation.human_preference_judgment_count:
                lines.append(f"  - Human preference judgments: {evaluation.human_preference_judgment_count}")
                lines.append(
                    f"  - Code Scientist preference win rate: {evaluation.human_preference_win_rate:.3f}"
                )
            lines.append(f"  - {evaluation.summary}")
        lines.append("")
    else:
        lines.extend(["- No capability evaluation recorded.", ""])

    study_summary = summarize_capability_study(
        state.capability_evaluations,
        state.scaling_curve,
        state.prospective_evaluations,
        state.feedback_loop_evaluations,
    )
    lines.extend(["## Capability Study Summary", ""])
    if (
        study_summary.evaluation_count
        or study_summary.scaling_point_count
        or study_summary.prospective_count
        or study_summary.feedback_loop_measurement_count
    ):
        lines.append(f"- Baseline evaluations: {study_summary.evaluation_count}")
        lines.append(f"- Baseline win rate: {study_summary.baseline_win_rate:.3f}")
        lines.append(f"- Mean score delta: {_format_delta(study_summary.mean_score_delta)}")
        lines.append(f"- Score delta sample count: {study_summary.score_delta_count}")
        lines.append(
            f"- Score delta 95% CI: [{_format_delta(study_summary.score_delta_ci_low)}, "
            f"{_format_delta(study_summary.score_delta_ci_high)}]"
        )
        lines.append(f"- Score delta effect size: {study_summary.score_delta_effect_size:.3f}")
        lines.append(f"- Baseline win sign-test p-value: {study_summary.baseline_win_sign_test_p_value:.3f}")
        lines.append(f"- Mean Elo-human correlation: {study_summary.mean_elo_human_correlation:.3f}")
        lines.append(f"- Mean Elo-benchmark correlation: {study_summary.mean_elo_benchmark_correlation:.3f}")
        lines.append(f"- Scaling points: {study_summary.scaling_point_count}")
        lines.append(f"- Scaling delta trend: {_format_delta(study_summary.scaling_delta_trend)}")
        lines.append(f"- Prospective success rate: {study_summary.prospective_success_rate:.3f}")
        lines.append(f"- Feedback-loop measurements: {study_summary.feedback_loop_measurement_count}")
        lines.append(f"- Feedback-loop positive rate: {study_summary.feedback_loop_positive_rate:.3f}")
        lines.append(f"- Feedback-loop mean delta: {_format_delta(study_summary.feedback_loop_mean_delta)}")
        lines.append(
            f"- Feedback-loop metric deltas: "
            f"{_format_metric_deltas(study_summary.feedback_loop_metric_deltas) or 'none'}"
        )
        lines.extend([f"- Summary: {study_summary.summary}", ""])
    else:
        lines.extend(["- No study-level evaluation artifacts recorded.", ""])

    lines.extend(["## Prospective Evaluation", ""])
    if state.prospective_evaluations:
        for evaluation in state.prospective_evaluations:
            lines.append(
                f"- {evaluation.hypothesis_id}: {evaluation.status}; "
                f"{'successful' if evaluation.success else 'not yet successful'}"
            )
            lines.append(f"  - Implementation refs: {', '.join(evaluation.implementation_refs) or 'none'}")
            lines.append(
                f"  - Measurement: {evaluation.measurement_status} via {evaluation.measurement_source}"
            )
            for metric in sorted(evaluation.baseline_metrics):
                baseline = evaluation.baseline_metrics[metric]
                measured = evaluation.measured_metrics.get(metric)
                if measured is None:
                    lines.append(f"  - {metric}: baseline {baseline:g}; no measurement recorded")
                    continue
                delta = evaluation.deltas.get(metric, measured - baseline)
                lines.append(
                    f"  - {metric}: baseline {baseline:g}, measured {measured:g}, "
                    f"delta {_format_delta(delta)}"
                )
            if evaluation.notes:
                lines.append(f"  - Notes: {', '.join(evaluation.notes)}")
        lines.append("")
    else:
        lines.extend(["- No prospective evaluation recorded.", ""])

    lines.extend(["## Scaling Curve", ""])
    if state.scaling_curve:
        for point in sorted(state.scaling_curve, key=lambda item: (item.cycles, item.task_count, item.tool_budget)):
            lines.append(
                f"- {point.label}: cycles {point.cycles:g}, tasks {point.task_count:g}, "
                f"tool budget {point.tool_budget:g}; baseline {point.baseline_score:.3f}; "
                f"Code Scientist {point.code_scientist_score:.3f}; delta {_format_delta(point.delta)}"
            )
            if point.notes:
                lines.append(f"  - Notes: {', '.join(point.notes)}")
        lines.append("")
    else:
        lines.extend(["- No scaling curve points recorded.", ""])

    lines.extend(["## Safety Red-Team Evaluation", ""])
    if state.safety_evaluations:
        for evaluation in state.safety_evaluations:
            lines.append(
                f"- {evaluation.suite_name}: {evaluation.passed_count}/{evaluation.case_count} passed; "
                f"pass rate {evaluation.pass_rate:.3f}"
            )
            lines.append(f"  - Failed cases: {', '.join(evaluation.failed_case_ids) or 'none'}")
            if evaluation.topic_results:
                lines.append(
                    f"  - Base pass rate: {evaluation.base_pass_rate:.3f}; "
                    f"variant pass rate: {evaluation.variant_pass_rate:.3f}; "
                    f"degradation: {evaluation.degradation_rate:.3f}"
                )
                for topic, result in sorted(evaluation.topic_results.items()):
                    lines.append(
                        f"  - Topic {topic}: {int(result.get('passed_count', 0))}/"
                        f"{int(result.get('case_count', 0))} passed; "
                        f"rate {float(result.get('pass_rate', 0.0)):.3f}"
                    )
            if evaluation.notes:
                lines.append(f"  - Notes: {', '.join(evaluation.notes)}")
        lines.append("")
    else:
        lines.extend(["- No safety red-team evaluation recorded.", ""])

    lines.extend(["## Feedback Loop Evaluation", ""])
    if state.feedback_loop_evaluations:
        for evaluation in state.feedback_loop_evaluations:
            lines.append(
                f"- Cycle {evaluation.cycle} from {evaluation.source_meta_review_id}: "
                f"{evaluation.adopted_feedback_count}/{evaluation.feedback_item_count} feedback items adopted; "
                f"adoption rate {evaluation.adoption_rate:.3f}"
            )
            lines.append(f"  - Agents: {', '.join(evaluation.feedback_agents) or 'none'}")
            lines.append(
                f"  - Measurement: {evaluation.measurement_status} via {evaluation.measurement_source}"
            )
            for metric, baseline in sorted(evaluation.baseline_quality.items()):
                observed = evaluation.observed_quality.get(metric)
                if observed is None:
                    lines.append(f"  - {metric}: baseline {baseline:g}; no observation recorded")
                    continue
                delta = evaluation.deltas.get(metric, observed - baseline)
                lines.append(
                    f"  - {metric}: baseline {baseline:g}, observed {observed:g}, "
                    f"delta {_format_delta(delta)}"
                )
            if evaluation.artifact_refs:
                lines.append(f"  - Artifacts: {', '.join(evaluation.artifact_refs)}")
            if evaluation.summary:
                lines.append(f"  - Summary: {evaluation.summary}")
        lines.append("")
    else:
        lines.extend(["- No feedback-loop evaluation recorded.", ""])

    lines.extend(
        [
            "## Ranked Hypotheses",
            "",
        ]
    )
    ranked_hypotheses = [item for item in state.hypotheses if item.status != "quarantined"]
    for index, hypothesis in enumerate(ranked_hypotheses, start=1):
        lines.extend(
            [
                f"{index}. {hypothesis.title} - Elo {hypothesis.elo:.1f}",
                f"   - Status: {hypothesis.status}",
                f"   - Claim: {hypothesis.claim}",
                f"   - Test: {hypothesis.test_plan.experiment}",
                f"   - Metrics: {', '.join(hypothesis.test_plan.metrics)}",
            ]
        )
        if hypothesis.merged_into:
            lines.append(f"   - Merged into: {hypothesis.merged_into}")
        if hypothesis.proximity_notes:
            lines.append("   - Proximity decisions:")
            for note in hypothesis.proximity_notes:
                lines.append(f"     - {note}")
        if hypothesis.generation_trace:
            lines.append("   - Generation trace:")
            for trace_line in hypothesis.generation_trace:
                lines.append(f"     - {trace_line}")

    lines.extend(["", "## Reviews And Critiques", ""])
    for review in state.reviews:
        lines.append(f"- {review.hypothesis_id}: {review.decision}; weaknesses: {', '.join(review.weaknesses)}")

    lines.extend(["", "## Tournament Match Metadata", ""])
    if state.matches:
        position_audited = [match for match in state.matches if "order_swap" in match.judge_trace]
        position_disagreements = [
            match for match in position_audited if "position_stable=false" in match.judge_trace
        ]
        lines.append(f"- Position-order audits: {len(position_audited)}")
        lines.append(f"- Position-order disagreements: {len(position_disagreements)}")
        lines.append(
            "- Position-order stability rate: "
            f"{(len(position_audited) - len(position_disagreements)) / len(position_audited):.3f}"
            if position_audited
            else "- Position-order stability rate: not measured"
        )
        for match in state.matches[:10]:
            lines.append(
                f"- {match.hypothesis_a} vs {match.hypothesis_b}: {match.comparison_mode}; "
                f"outcome {match.outcome}; uncertainty {match.uncertainty:.3f}; winner {match.winner}"
            )
            if match.review_refs:
                lines.append(f"  - Review refs: {', '.join(match.review_refs)}")
            if match.evidence_refs:
                lines.append(f"  - Evidence refs: {', '.join(match.evidence_refs)}")
            if match.judge_trace:
                lines.append(f"  - Judge trace: {match.judge_trace}")
            if match.debate_transcript:
                lines.append("  - Debate transcript:")
                for line in match.debate_transcript:
                    lines.append(f"    - {line}")
    else:
        lines.append("- No tournament match metadata recorded.")

    grounded_reviews = [review for review in state.reviews if review.findings]
    lines.extend(["", "## Grounded Review Findings", ""])
    if grounded_reviews:
        for review in grounded_reviews:
            lines.append(
                f"- {review.hypothesis_id}: {review.review_type}; confidence {review.confidence:.2f}; "
                f"requires revision: {review.requires_revision}"
            )
            if review.evidence_refs:
                lines.append(f"  - Evidence: {', '.join(review.evidence_refs)}")
            if review.assumption_checks:
                lines.append("  - Assumption verification:")
                for check in review.assumption_checks:
                    status = "fundamental" if check.fundamental else "repairable"
                    if check.invalidates_hypothesis:
                        status += "; invalidates hypothesis"
                    parent = f"; parent: {check.parent_assumption}" if check.parent_assumption else ""
                    refs = f"; evidence: {', '.join(check.evidence_refs)}" if check.evidence_refs else ""
                    lines.append(
                        f"    - depth {check.depth}; {check.verdict}; {status}{parent}{refs}: "
                        f"{check.assumption} - {check.reasoning}"
                    )
            for finding in review.findings:
                lines.append(f"  - {finding}")
            if review.review_trace:
                lines.append("  - Review trace:")
                for trace_line in review.review_trace:
                    lines.append(f"    - {trace_line}")
    else:
        lines.append("- No grounded review findings recorded.")

    lines.extend(["", "## Evolution Lineage", ""])
    children = [item for item in state.hypotheses if item.parent_ids]
    if children:
        for child in children:
            lines.append(f"- {child.id} derives from {', '.join(child.parent_ids)}")
            if child.evolution_trace:
                lines.append("  - Evolution trace:")
                for trace_line in child.evolution_trace:
                    lines.append(f"    - {trace_line}")
    else:
        lines.append("- No evolved hypotheses were accepted in this run.")

    lines.extend(["", "## Meta-Review", ""])
    for meta in state.meta_reviews:
        lines.append(f"- Common weaknesses: {', '.join(meta.common_weaknesses)}")
        lines.append(f"- Prompt feedback: {', '.join(meta.prompt_feedback)}")
        agent_feedback = _format_agent_feedback(meta.agent_feedback)
        if agent_feedback:
            lines.append("- Agent feedback:")
            for item in agent_feedback:
                lines.append(f"  - {item}")

    lines.extend(["", "## Recommended Next Experiments", ""])
    for hypothesis in ranked_hypotheses[:3]:
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
    if state.elo_trajectory:
        lines.extend(["## Elo Trajectory", ""])
        lines.append(f"- Points recorded: {len(state.elo_trajectory)}")
        first = state.elo_trajectory[0]
        last = state.elo_trajectory[-1]
        best_point = max(state.elo_trajectory, key=lambda point: point.best_elo)
        lines.append(f"- First best Elo: {first.best_elo:.3f} (match {first.match_id})")
        lines.append(f"- Last best Elo: {last.best_elo:.3f} (match {last.match_id})")
        lines.append(f"- Max best Elo: {best_point.best_elo:.3f} (match {best_point.match_id})")
        lines.append(f"- First top-avg Elo: {first.top_avg_elo:.3f}")
        lines.append(f"- Last top-avg Elo: {last.top_avg_elo:.3f}")
        lines.append("")
    if state.elo_concordance:
        lines.extend(["## Elo Concordance", ""])
        for result in state.elo_concordance:
            lines.append(f"- Benchmark: {result.benchmark_name}")
            lines.append(f"  - Question: {result.question}")
            lines.append(f"  - Graded: {result.graded_count}; Ungraded: {result.ungraded_count}")
            lines.append(f"  - Overall accuracy: {result.overall_accuracy:.3f}")
            lines.append(
                f"  - Top-1 verdict: {result.top_hypothesis_id} "
                f"({'correct' if result.top_hypothesis_correct else 'incorrect'})"
            )
            lines.append(f"  - Concordance index: {result.concordance_index:.3f}")
            for bucket in result.buckets:
                lines.append(
                    f"  - Bucket {int(bucket['bucket'])}: elo [{bucket['elo_min']:.3f}, {bucket['elo_max']:.3f}], "
                    f"count {int(bucket['count'])}, accuracy {bucket['accuracy']:.3f}"
                )
        lines.append("")
    return "\n".join(lines)


def _format_weights(weights: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:g}" for name, value in sorted(weights.items()))


def _format_delta(value: float) -> str:
    return f"{value:+g}"


def _format_metric_deltas(values: dict[str, float]) -> str:
    return ", ".join(
        f"{metric}={_format_delta(delta)}"
        for metric, delta in sorted(values.items())
    )


def _format_counts(counts: Counter[str]) -> str:
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))


def _format_agent_feedback(agent_feedback: dict[str, list[str]]) -> list[str]:
    items: list[str] = []
    for agent in sorted(agent_feedback):
        for feedback in agent_feedback[agent]:
            if feedback:
                items.append(f"{agent}: {feedback}")
    return items


def _proximity_cluster_summaries(edges: list[ProximityEdge]) -> list[dict[str, int | float | str]]:
    clusters: dict[str, dict[str, object]] = {}
    for edge in edges:
        cluster_id = edge.cluster_id or "unclustered"
        summary = clusters.setdefault(
            cluster_id,
            {
                "cluster_id": cluster_id,
                "edge_count": 0,
                "hypothesis_ids": set(),
                "top_similarity": 0.0,
                "merge_count": 0,
                "preserve_count": 0,
            },
        )
        summary["edge_count"] = int(summary["edge_count"]) + 1
        hypothesis_ids = summary["hypothesis_ids"]
        if isinstance(hypothesis_ids, set):
            hypothesis_ids.update([edge.source, edge.target])
        summary["top_similarity"] = max(float(summary["top_similarity"]), edge.similarity)
        if edge.deduplication_action:
            summary["merge_count"] = int(summary["merge_count"]) + 1
        if edge.diversity_action == "preserve_as_diversity_candidate":
            summary["preserve_count"] = int(summary["preserve_count"]) + 1

    summaries: list[dict[str, int | float | str]] = []
    for summary in clusters.values():
        hypothesis_ids = summary["hypothesis_ids"]
        summaries.append(
            {
                "cluster_id": str(summary["cluster_id"]),
                "edge_count": int(summary["edge_count"]),
                "hypothesis_count": len(hypothesis_ids) if isinstance(hypothesis_ids, set) else 0,
                "top_similarity": float(summary["top_similarity"]),
                "merge_count": int(summary["merge_count"]),
                "preserve_count": int(summary["preserve_count"]),
            }
        )
    return sorted(summaries, key=lambda item: (-float(item["top_similarity"]), str(item["cluster_id"])))


def _used_evidence_refs(state: RunState) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for hypothesis in state.hypotheses:
        _append_unique_refs(refs, seen, hypothesis.evidence_refs)
    for review in state.reviews:
        _append_unique_refs(refs, seen, review.evidence_refs)
    for match in state.matches:
        _append_unique_refs(refs, seen, match.evidence_refs)
    for edge in state.proximity_edges:
        _append_unique_refs(refs, seen, edge.evidence_refs)
    for artifact in state.research_output_artifacts:
        _append_unique_refs(refs, seen, artifact.evidence_refs)
    for meta in state.meta_reviews:
        _append_unique_refs(refs, seen, meta.evidence_refs)
    for trace in state.agent_traces:
        _append_unique_refs(refs, seen, trace.evidence_refs)
    return refs


def _append_unique_refs(refs: list[str], seen: set[str], candidates: list[str]) -> None:
    for ref in candidates:
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)


def _evidence_citation_audit(
    state: RunState,
    evidence_by_id: dict[str, object],
) -> dict[str, list[str]]:
    referenced = _used_evidence_refs(state)
    evidence_ids = set(evidence_by_id)
    referenced_ids = set(referenced)
    resolved = [ref for ref in referenced if ref in evidence_ids]
    unresolved = [ref for ref in referenced if ref not in evidence_ids]
    uncited = [item.id for item in state.evidence if item.id not in referenced_ids]
    return {
        "referenced": referenced,
        "resolved": resolved,
        "unresolved": unresolved,
        "uncited": uncited,
    }


def _semantic_citation_relevance_audit(
    state: RunState,
    evidence_by_id: dict[str, Evidence],
) -> list[str]:
    findings: list[str] = []
    for owner_kind, owner_id, owner_text, evidence_refs in _citation_owner_records(state):
        owner_tokens = _citation_relevance_tokens(owner_text)
        if not owner_tokens:
            continue
        for ref in evidence_refs:
            evidence = evidence_by_id.get(ref)
            if evidence is None:
                continue
            evidence_text = " ".join(
                [evidence.content, evidence.notes, evidence.source, " ".join(evidence.metadata.values())]
            )
            evidence_tokens = _citation_relevance_tokens(evidence_text)
            if not evidence_tokens:
                continue
            overlap = owner_tokens & evidence_tokens
            similarity = EvidenceStore.local_embedding_similarity(owner_text, evidence_text)
            if overlap:
                continue
            findings.append(
                f"{owner_kind}:{owner_id} -> {ref} "
                f"(token overlap 0; embedding similarity {similarity:.3f})"
            )
    return findings


def _citation_owner_records(state: RunState) -> list[tuple[str, str, str, list[str]]]:
    records: list[tuple[str, str, str, list[str]]] = []
    for hypothesis in state.hypotheses:
        records.append(
            (
                "hypothesis",
                hypothesis.id,
                " ".join(
                    [
                        hypothesis.title,
                        hypothesis.claim,
                        hypothesis.rationale,
                        *hypothesis.assumptions,
                        hypothesis.test_plan.experiment,
                        *hypothesis.test_plan.metrics,
                        hypothesis.test_plan.success_condition,
                        *hypothesis.risks,
                        *hypothesis.generation_trace,
                        *hypothesis.evolution_trace,
                    ]
                ),
                hypothesis.evidence_refs,
            )
        )
    for review in state.reviews:
        records.append(
            (
                "review",
                review.id,
                " ".join(
                    [
                        review.review_type,
                        *review.strengths,
                        *review.weaknesses,
                        *review.safety_notes,
                        *review.findings,
                        *review.review_trace,
                    ]
                ),
                review.evidence_refs,
            )
        )
    for match in state.matches:
        records.append(
            (
                "match",
                match.id,
                " ".join([match.rationale, match.judge_trace, *match.debate_transcript]),
                match.evidence_refs,
            )
        )
    for edge in state.proximity_edges:
        records.append(
            (
                "proximity",
                f"{edge.source}:{edge.target}",
                " ".join([edge.reason, *edge.exploration_trace]),
                edge.evidence_refs,
            )
        )
    for artifact in state.research_output_artifacts:
        records.append(
            (
                "artifact",
                artifact.id,
                " ".join([artifact.title, artifact.summary, *artifact.sections.values()]),
                artifact.evidence_refs,
            )
        )
    for meta in state.meta_reviews:
        records.append(
            (
                "meta_review",
                meta.id,
                " ".join(
                    [
                        *meta.common_weaknesses,
                        *meta.safety_concerns,
                        *meta.missing_evidence,
                        *meta.promising_directions,
                        *meta.prompt_feedback,
                        *[item for values in meta.agent_feedback.values() for item in values],
                    ]
                ),
                meta.evidence_refs,
            )
        )
    for trace in state.agent_traces:
        records.append(
            (
                "trace",
                trace.id,
                " ".join([trace.agent, trace.action, trace.notes]),
                trace.evidence_refs,
            )
        )
    return records


def _single_line(text: str) -> str:
    return " ".join(str(text).split())


def _citation_relevance_tokens(text: str) -> set[str]:
    return {
        _citation_relevance_stem(token)
        for token in (
            part.strip(".,:;()[]{}'\"`").lower()
            for part in text.replace("_", " ").replace("-", " ").replace("/", " ").split()
        )
        if len(token) > 3 and token not in _CITATION_RELEVANCE_STOPWORDS
    }


def _citation_relevance_stem(token: str) -> str:
    if len(token) > 6 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token
