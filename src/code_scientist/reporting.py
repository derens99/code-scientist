from __future__ import annotations

from collections import Counter

from code_scientist.benchmarks import summarize_benchmark_comparison_study
from code_scientist.evidence import EvidenceStore
from code_scientist.evaluation import (
    audit_capability_study_coverage,
    summarize_capability_study,
    summarize_capability_study_from_states,
)
from code_scientist.models import BenchmarkResult, Evidence, ProximityEdge, RunState


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
        f"- Missing requirements: {', '.join(coverage.missing_requirements) or 'none'}",
        f"- Summary: {coverage.summary}",
        "",
    ]
    if states:
        lines.extend(["## Included Goals", ""])
        for state in states:
            lines.append(f"- {state.goal.objective}")
        lines.append("")
    return "\n".join(lines)


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
            if trace.notes:
                lines.append(f"  - Notes: {trace.notes}")
            if trace.evidence_refs:
                lines.append(f"  - Evidence: {', '.join(trace.evidence_refs)}")
            if trace.scratchpad:
                lines.append("  - Scratchpad:")
                for note in trace.scratchpad[:5]:
                    lines.append(f"    - {_single_line(note)[:240]}")
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
    for index, hypothesis in enumerate(state.hypotheses, start=1):
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
