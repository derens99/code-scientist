from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any

from code_scientist.agents import (
    EvolutionAgent,
    GenerationAgent,
    MetaReviewAgent,
    ProximityAgent,
    RankingAgent,
    ReflectionAgent,
)
from code_scientist.evaluation import load_capability_evaluation_fixtures
from code_scientist.evidence import EvidenceStore, merge_evidence, read_document_text
from code_scientist.llm import DEFAULT_ANTHROPIC_MODEL, AnthropicHaikuClient, LLMResponseError
from code_scientist.models import (
    AgentTrace,
    BenchmarkResult,
    ContextSnapshot,
    Evidence,
    EvidenceSafetyFinding,
    FeedbackLoopEvaluation,
    Hypothesis,
    Match,
    MetaReview,
    ProximityEdge,
    ResearchGoal,
    ResearchOverview,
    ResearchOutputArtifact,
    ResearchPlanConfig,
    RetrievalMemoryRecord,
    Review,
    RunState,
    Task,
    UserFeedback,
    stable_id,
)
from code_scientist.paper import seed_paper_evidence
from code_scientist.planning import parse_research_plan_with_llm
from code_scientist.safety import (
    _safety_rejected_hypothesis_ids,
    SafetyPolicy,
    load_safety_policies,
    review_goal_safety,
    review_goal_safety_with_model,
    review_hypothesis_safety,
    screen_evidence_sources,
)
from code_scientist.tools import (
    collect_literature_search_evidence,
    collect_local_repo_search_evidence,
    collect_web_evidence,
    collect_web_search_evidence,
)


_INACTIVE_STATUSES = {"merged_duplicate", "quarantined"}


def _active_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    return [item for item in hypotheses if item.status not in _INACTIVE_STATUSES]


# Default-plan termination strings that describe run-level bounds enforced
# elsewhere (fixed cycle count, max hypotheses, human/control-file stop). They
# are silently skipped here rather than reported as unevaluated.
_TERMINATION_IGNORE = {"max_cycles", "max_hypotheses", "human_stop"}
_ELO_PLATEAU_DEFAULT = 2


def _termination_criterion_kind(normalized: str) -> str:
    """Classify a normalized (stripped, lowercased) termination criterion."""
    if normalized.startswith("min_hypotheses") or (
        "at least" in normalized and "hypothes" in normalized
    ):
        return "min_hypotheses"
    if normalized.startswith("elo_plateau") or "elo plateau" in normalized:
        return "elo_plateau"
    if normalized == "all_reviewed" or "all reviewed" in normalized:
        return "all_reviewed"
    return "unevaluated"


def unevaluated_termination_markers(plan: ResearchPlanConfig) -> list[str]:
    """Pure helper: ``unevaluated:<text>`` markers for plan termination criteria
    the deterministic evaluator does not recognize (ignore-set entries excluded).
    """
    markers: list[str] = []
    for raw in plan.termination_criteria:
        criterion = raw.strip()
        normalized = criterion.lower()
        if not normalized or normalized in _TERMINATION_IGNORE:
            continue
        if _termination_criterion_kind(normalized) != "unevaluated":
            continue
        marker = f"unevaluated:{criterion}"
        if marker not in markers:
            markers.append(marker)
    return markers


def evaluate_termination_criteria(
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    context_snapshots: list[ContextSnapshot],
) -> str | None:
    """Deterministically evaluate free-text plan termination criteria.

    Pure: reads its arguments and returns a stable reason string for the first
    criterion that fires, or None when no criterion terminates the run.
    Unrecognized criteria never terminate; callers surface them via
    ``unevaluated_termination_markers`` (recorded on snapshot ``next_actions``).
    """

    active = _active_hypotheses(hypotheses)

    for raw in plan.termination_criteria:
        normalized = raw.strip().lower()
        if not normalized or normalized in _TERMINATION_IGNORE:
            continue

        kind = _termination_criterion_kind(normalized)
        digits = re.findall(r"\d+", normalized)

        if kind == "min_hypotheses":
            threshold = int(digits[0]) if digits else 1
            if len(active) >= threshold:
                return f"min_hypotheses:{threshold}"

        elif kind == "elo_plateau":
            # Deterministic stand-in: an unchanged top-ranked hypothesis id
            # across the window approximates an Elo plateau; real Elo-history
            # deltas arrive in a later wave.
            window = int(digits[0]) if digits else _ELO_PLATEAU_DEFAULT
            if window >= 1 and len(context_snapshots) >= window:
                recent = context_snapshots[-window:]
                tops = [snapshot.top_hypothesis_ids[:1] for snapshot in recent]
                if all(top and top == tops[0] for top in tops):
                    return f"elo_plateau:{window}"

        elif kind == "all_reviewed":
            if active:
                reviewed_ids = {review.hypothesis_id for review in reviews}
                if all(item.id in reviewed_ids for item in active):
                    return "all_reviewed"

    return None


def run_research_cycle(
    objective: str,
    cycles: int,
    max_hypotheses: int,
    max_matches: int,
    out_dir: str | Path,
    provider: str = "deterministic",
    model: str | None = None,
    max_tokens: int = 1024,
    env_file: str | Path = ".env",
    llm_client: Any | None = None,
    goal_brief_paths: list[str | Path] | None = None,
    safety_policy_paths: list[str | Path] | None = None,
    benchmark_results: list[BenchmarkResult] | None = None,
    evidence_paths: list[str | Path] | None = None,
    evidence_index_paths: list[str | Path] | None = None,
    repo_search_paths: list[str | Path] | None = None,
    web_evidence_urls: list[str] | None = None,
    web_crawl_depth: int = 0,
    web_search_queries: list[str] | None = None,
    web_search_fetch: bool = False,
    web_search_crawl_depth: int = 0,
    literature_search_queries: list[str] | None = None,
    literature_full_text: bool = False,
    capability_evaluation_paths: list[str | Path] | None = None,
    plan_config: ResearchPlanConfig | None = None,
    resume: bool = False,
    run_status: str = "completed",
    control_path: str | Path | None = None,
) -> RunState:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    state_path = out_path / "state.json"
    existing_state = load_state(state_path) if resume and state_path.exists() else None
    goal = (
        existing_state.goal
        if existing_state
        else ResearchGoal.from_objective_with_briefs(objective, _read_goal_briefs(goal_brief_paths or []))
    )
    model_client = _build_model_client(
        provider=provider,
        model=model,
        env_file=env_file,
        llm_client=llm_client,
    )
    safety_policies = load_safety_policies(safety_policy_paths or [])
    plan = (
        existing_state.plan or plan_config or _plan_for_goal(goal, provider, model_client, max_tokens)
        if existing_state
        else plan_config or _plan_for_goal(goal, provider, model_client, max_tokens)
    )
    safety_llm_client = model_client if provider == "anthropic" else None
    safety_fail_closed = any(policy.fail_closed for policy in safety_policies)
    safety = (
        existing_state.safety
        or review_goal_safety_with_model(
            _goal_safety_text(goal),
            safety_llm_client,
            max_tokens=max_tokens,
            safety_policies=safety_policies,
            fail_closed=safety_fail_closed,
        )
        if existing_state
        else review_goal_safety_with_model(
            _goal_safety_text(goal),
            safety_llm_client,
            max_tokens=max_tokens,
            safety_policies=safety_policies,
            fail_closed=safety_fail_closed,
        )
    )
    benchmarks = benchmark_results if benchmark_results is not None else (existing_state.benchmark_results if existing_state else [])
    governed_evidence, governance_findings = _collect_plan_governed_evidence(
        goal=goal,
        plan=plan,
        evidence_paths=evidence_paths or [],
        evidence_index_paths=evidence_index_paths or [],
        repo_search_paths=repo_search_paths or [],
        web_evidence_urls=web_evidence_urls or [],
        web_crawl_depth=web_crawl_depth,
        web_search_queries=web_search_queries or [],
        web_search_fetch=web_search_fetch,
        web_search_crawl_depth=web_search_crawl_depth,
        literature_search_queries=literature_search_queries or [],
        literature_full_text=literature_full_text,
        safety_policies=safety_policies,
    )
    merged_evidence = merge_evidence(
        existing_state.evidence if existing_state else seed_paper_evidence(),
        governed_evidence,
    )
    evidence, evidence_safety_findings = screen_evidence_sources(
        merged_evidence,
        llm_client=safety_llm_client,
        max_tokens=max_tokens,
        safety_policies=safety_policies,
        fail_closed=safety_fail_closed,
    )
    evidence_safety_findings = _merge_evidence_safety_findings(
        existing_state.evidence_safety_findings if existing_state else [],
        governance_findings,
        evidence_safety_findings,
    )
    use_grounded_review = bool(governed_evidence)
    state = (
        replace(
            existing_state,
            run_status=run_status,
            benchmark_results=benchmarks,
            evidence=evidence,
            evidence_safety_findings=evidence_safety_findings,
        )
        if existing_state
        else RunState(
            goal=goal,
            run_status=run_status,
            plan=plan,
            evidence=evidence,
            evidence_safety_findings=evidence_safety_findings,
            benchmark_results=benchmarks,
            safety=safety,
        )
    )
    if not safety.allowed:
        blocked_state = replace(state, run_status="blocked")
        _write_state(state_path, blocked_state)
        return blocked_state

    generation = _build_generation_agent(
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        env_file=env_file,
        llm_client=model_client,
    )
    agent_llm_client = model_client if provider == "anthropic" else None
    reflection = ReflectionAgent(
        llm_client=agent_llm_client,
        llm_max_tokens=max_tokens,
        safety_policies=safety_policies,
    )
    proximity = ProximityAgent(llm_client=agent_llm_client, llm_max_tokens=max_tokens)
    ranking = RankingAgent(llm_client=agent_llm_client, llm_max_tokens=max_tokens)
    evolution = EvolutionAgent(llm_client=agent_llm_client, llm_max_tokens=max_tokens)
    meta_review = MetaReviewAgent(llm_client=agent_llm_client, llm_max_tokens=max_tokens)
    evidence_store = EvidenceStore(state.evidence)

    hypotheses: list[Hypothesis] = list(state.hypotheses)
    reviews: list[Review] = list(state.reviews)
    hypotheses, ingestion_safety_reviews = _quarantine_unsafe_loaded_hypotheses(
        hypotheses,
        reviews,
        safety_policies=safety_policies,
    )
    reviews = [*reviews, *ingestion_safety_reviews]
    matches: list[Match] = list(state.matches)
    proximity_edges: list[ProximityEdge] = list(state.proximity_edges)
    capability_evaluations = list(state.capability_evaluations)
    prospective_evaluations = list(state.prospective_evaluations)
    scaling_curve = list(state.scaling_curve)
    safety_evaluations = list(state.safety_evaluations)
    feedback_loop_evaluations = list(state.feedback_loop_evaluations)
    research_output_artifacts = list(state.research_output_artifacts)
    metas = list(state.meta_reviews)
    context_snapshots: list[ContextSnapshot] = list(state.context_snapshots)
    research_overview = state.research_overview
    user_feedback = list(state.user_feedback)
    agent_traces = list(state.agent_traces)
    retrieval_memory = list(state.retrieval_memory)
    task_queue = prepare_task_queue_for_resume(list(state.task_queue)) if resume else list(state.task_queue)
    feedback: list[str] = metas[-1].prompt_feedback if metas else []
    start_cycle = (context_snapshots[-1].cycle + 1) if context_snapshots else 1
    control_file = Path(control_path) if control_path else None
    deferred_run_status = run_status

    def current_state(status: str, queue: list[Task]) -> RunState:
        return RunState(
            goal=goal,
            run_status=status,
            plan=plan,
            evidence=evidence,
            evidence_safety_findings=evidence_safety_findings,
            hypotheses=sorted(hypotheses, key=lambda item: item.elo, reverse=True),
            reviews=reviews,
            matches=matches,
            proximity_edges=proximity_edges,
            benchmark_results=benchmarks,
            capability_evaluations=capability_evaluations,
            prospective_evaluations=prospective_evaluations,
            scaling_curve=scaling_curve,
            safety_evaluations=safety_evaluations,
            feedback_loop_evaluations=feedback_loop_evaluations,
            research_output_artifacts=research_output_artifacts,
            meta_reviews=metas,
            context_snapshots=context_snapshots,
            safety=safety,
            research_overview=research_overview,
            user_feedback=user_feedback,
            agent_traces=agent_traces,
            retrieval_memory=retrieval_memory,
            task_queue=queue,
        )

    def persist_current_task_state(queue: list[Task]) -> None:
        _write_state(state_path, current_state(run_status, queue))

    def defer_reason_from_control() -> str | None:
        nonlocal deferred_run_status
        if control_file is None:
            return None
        action = _read_control_action(control_file)
        if action not in {"pause", "stop"}:
            return None
        deferred_run_status = "paused" if action == "pause" else "stopped"
        return f"{action} requested by control file"

    try:
        for cycle in range(start_cycle, start_cycle + cycles):
            source_feedback_meta = metas[-1] if metas else None
            baseline_feedback_quality = _feedback_quality_metrics(hypotheses, reviews)
            task_handlers: dict[str, Callable[[Task], list[str] | None]] = {}

            def schedule_cycle_task(
                kind: str,
                payload: dict[str, Any],
                execute: Callable[[Task], list[str] | None],
            ) -> Task:
                nonlocal task_queue
                task = create_task(cycle=cycle, plan=plan, kind=kind, payload=payload)
                task = replace(
                    task,
                    priority=score_task_priority(
                        task,
                        plan=plan,
                        hypotheses=hypotheses,
                        reviews=reviews,
                        proximity_edges=proximity_edges,
                        user_feedback=user_feedback,
                        current_cycle=cycle,
                        context_snapshots=context_snapshots,
                    ),
                )
                existing_task_index = next(
                    (
                        index
                        for index, existing in enumerate(task_queue)
                        if existing.id == task.id and existing.status != "completed"
                    ),
                    None,
                )
                if existing_task_index is None:
                    task_queue = [*task_queue, task]
                else:
                    task_queue = [
                        *task_queue[:existing_task_index],
                        replace(
                            task_queue[existing_task_index],
                            priority=task.priority,
                            payload=task.payload,
                        ),
                        *task_queue[existing_task_index + 1 :],
                    ]
                task_handlers[task.id] = execute
                return task

            def run_ready_cycle_tasks(eligible_task_ids: set[str]) -> None:
                nonlocal task_queue

                def execute_scheduled_task(task: Task) -> list[str] | None:
                    handler = task_handlers.get(task.id)
                    if handler is None:
                        raise RuntimeError(f"No scheduler handler registered for task: {task.id}")
                    return handler(task)

                scheduler_pool = select_scheduler_task_pool(
                    task_queue,
                    plan=plan,
                    hypotheses=hypotheses,
                    reviews=reviews,
                    proximity_edges=proximity_edges,
                    user_feedback=user_feedback,
                    current_cycle=cycle,
                    context_snapshots=context_snapshots,
                    max_pool_size=len(eligible_task_ids),
                    candidate_task_ids=eligible_task_ids,
                )
                selected_task_ids = {task.id for task in scheduler_pool}
                scheduler_selection_by_id = {task.id: task for task in scheduler_pool}
                rescored_queue = rescore_task_queue(
                    task_queue,
                    plan=plan,
                    hypotheses=hypotheses,
                    reviews=reviews,
                    proximity_edges=proximity_edges,
                    user_feedback=user_feedback,
                    current_cycle=cycle,
                    context_snapshots=context_snapshots,
                )
                task_queue = [
                    replace(
                        task,
                        priority=scheduler_selection_by_id[task.id].priority,
                        worker_state=scheduler_selection_by_id[task.id].worker_state,
                    )
                    if task.id in scheduler_selection_by_id
                    else task
                    for task in rescored_queue
                ]
                task_queue = run_task_worker(
                    task_queue,
                    execute=execute_scheduled_task,
                    persist=persist_current_task_state,
                    raise_on_failed=True,
                    eligible_task_ids=selected_task_ids,
                    defer_when=defer_reason_from_control,
                )
                for task_id in eligible_task_ids:
                    current_task = next((existing for existing in task_queue if existing.id == task_id), None)
                    if current_task and current_task.status == "deferred":
                        raise _TaskDeferred(deferred_run_status)

            def run_cycle_task(
                kind: str,
                payload: dict[str, Any],
                execute: Callable[[Task], list[str] | None],
            ) -> None:
                task = schedule_cycle_task(kind, payload, execute)
                run_ready_cycle_tasks({task.id})

            remaining = max(max_hypotheses - len(hypotheses), 0)
            active_generation_methods = _active_generation_methods(plan, use_grounded_review)
            generation_limit = remaining - min(2, remaining) if remaining > 2 else remaining
            if remaining:
                generation_limit = min(
                    remaining,
                    max(generation_limit, len(active_generation_methods)),
                )
            generation_allocations = _allocate_generation_methods(
                active_generation_methods,
                generation_limit,
                hypotheses=hypotheses,
                proximity_edges=proximity_edges,
            )
            existing_ids = {item.id for item in hypotheses}
            generation_feedback = _agent_feedback_for(metas, "generation")
            reflection_feedback = _agent_feedback_for(metas, "reflection")
            safety_feedback = _agent_feedback_for(metas, "safety")
            proximity_feedback = _agent_feedback_for(metas, "proximity")
            ranking_feedback = _agent_feedback_for(metas, "ranking")
            evolution_feedback = _unique_refs([*feedback, *_agent_feedback_for(metas, "evolution")])
            overview_feedback = _agent_feedback_for(metas, "overview")
            generated: list[Hypothesis] = []
            reviewed: list[Review] = []

            def execute_generation(_task: Task) -> list[str]:
                nonlocal generated
                generated_candidates = _generate_for_plan(
                    generation=generation,
                    goal=goal,
                    plan=plan,
                    evidence=evidence,
                    evidence_store=evidence_store,
                    limit=generation_limit,
                    use_grounded=use_grounded_review,
                    cycle=cycle,
                    agent_traces=agent_traces,
                    agent_feedback=generation_feedback,
                    task_id=_task.id,
                    existing_hypotheses=hypotheses,
                    proximity_edges=proximity_edges,
                    generation_allocations=generation_allocations,
                    retrieval_memory=retrieval_memory,
                )
                generated = [item for item in generated_candidates if item.id not in existing_ids]
                return [item.id for item in generated]

            def make_execute_review(target: Hypothesis) -> Callable[[Task], list[str]]:
                def execute_review(_task: Task) -> list[str]:
                    nonlocal hypotheses, reviewed
                    task_reviews = _review_for_plan(
                        reflection=reflection,
                        goal=goal,
                        plan=plan,
                        hypotheses=[target],
                        evidence_store=evidence_store,
                        use_grounded=use_grounded_review,
                        cycle=cycle,
                        agent_traces=agent_traces,
                        agent_feedback=reflection_feedback,
                        safety_feedback=safety_feedback,
                        task_id=_task.id,
                        retrieval_memory=retrieval_memory,
                    )
                    reviewed.extend(task_reviews)
                    accepted_ids = _accepted_hypothesis_ids([target], task_reviews)
                    accepted = [target.with_status("accepted")] if target.id in accepted_ids else []
                    hypotheses = _merge_hypotheses(hypotheses, accepted)
                    reviews.extend(task_reviews)
                    return [item.id for item in task_reviews]

                return execute_review

            def register_resumed_review_tasks() -> list[Task]:
                target_by_id = {item.id: item for item in hypotheses}
                registered: list[Task] = []
                for task in task_queue:
                    if task.status != "queued" or task.kind != "review":
                        continue
                    target_id = str(task.payload.get("hypothesis_id", ""))
                    target = target_by_id.get(target_id)
                    if target is None:
                        continue
                    task_handlers[task.id] = make_execute_review(target)
                    registered.append(task)
                return registered

            generation_task = schedule_cycle_task(
                "generate",
                {
                    "modes": active_generation_methods,
                    "generation_allocations": generation_allocations,
                    "agent_feedback": generation_feedback,
                },
                execute_generation,
            )
            initial_ready_tasks = register_resumed_review_tasks()
            run_ready_cycle_tasks({generation_task.id, *[task.id for task in initial_ready_tasks]})

            review_tasks = [
                schedule_cycle_task(
                    "review",
                    {
                        "review_types": _active_review_types(plan, use_grounded_review),
                        "hypothesis_id": item.id,
                        "hypothesis_ids": [item.id],
                        "agent_feedback": _unique_refs([*reflection_feedback, *safety_feedback]),
                    },
                    make_execute_review(item),
                )
                for item in generated
            ]
            if review_tasks:
                run_ready_cycle_tasks({task.id for task in review_tasks})

            def execute_empty_review(_task: Task) -> list[str]:
                nonlocal hypotheses, reviewed
                reviewed = _review_for_plan(
                    reflection=reflection,
                    goal=goal,
                    plan=plan,
                    hypotheses=[],
                    evidence_store=evidence_store,
                    use_grounded=use_grounded_review,
                    cycle=cycle,
                    agent_traces=agent_traces,
                    agent_feedback=reflection_feedback,
                    safety_feedback=safety_feedback,
                    task_id=_task.id,
                    retrieval_memory=retrieval_memory,
                )
                return [item.id for item in reviewed]

            if not review_tasks:
                run_cycle_task(
                    "review",
                    {
                        "review_types": _active_review_types(plan, use_grounded_review),
                        "hypothesis_ids": [],
                        "agent_feedback": _unique_refs([*reflection_feedback, *safety_feedback]),
                    },
                    execute_empty_review,
                )

            hypotheses = _apply_safety_quarantine(hypotheses, reviews)

            def execute_proximity(_task: Task) -> list[str]:
                nonlocal hypotheses, proximity_edges
                proximity_edges = proximity.compute_goal_aware(goal, hypotheses, reviews, evidence_store)
                proximity_edges = _apply_proximity_feedback(proximity_edges, proximity_feedback)
                hypotheses = _apply_proximity_deduplication(hypotheses, proximity_edges)
                task_retrievals = evidence_store.consume_retrieval_memory(
                    cycle=cycle,
                    agent="proximity",
                    task_id=_task.id,
                    reason="proximity relation retrieval",
                )
                retrieval_memory.extend(task_retrievals)
                edge_refs = [_pair_key(edge.source, edge.target) for edge in proximity_edges]
                method = _proximity_method(proximity_edges)
                proximity_notes = f"Computed {len(proximity_edges)} {method} proximity edges."
                deduplicated_total = len([item for item in hypotheses if item.status == "merged_duplicate"])
                if deduplicated_total:
                    proximity_notes += f" Deduplicated {deduplicated_total} hypotheses for active scheduling."
                if proximity_feedback:
                    proximity_notes += f" Agent feedback: {'; '.join(proximity_feedback)}."
                agent_traces.append(
                    _build_agent_trace(
                        cycle=cycle,
                        agent="proximity",
                        action=f"compute_{method}_edges",
                        input_refs=[item.id for item in hypotheses],
                        output_refs=edge_refs,
                        notes=proximity_notes,
                        evidence_refs=_evidence_refs_for_edges(proximity_edges),
                        task_id=_task.id,
                        llm_interactions=proximity.consume_llm_interactions(),
                        scratchpad=_trace_scratchpad(
                            [
                                f"method={method}",
                                f"edge_count={len(proximity_edges)}",
                                f"deduplicated={deduplicated_total}",
                            ],
                            task_retrievals,
                        ),
                        tool_calls=_tool_calls_from_retrievals(task_retrievals),
                    )
                )
                return edge_refs

            proximity_task = schedule_cycle_task(
                "proximity",
                {
                    "method": "goal_aware",
                    "hypothesis_ids": [item.id for item in hypotheses],
                    "agent_feedback": proximity_feedback,
                },
                execute_proximity,
            )

            def execute_ranking(_task: Task) -> list[str]:
                nonlocal hypotheses
                cycle_match_ids: list[str] = []
                cycle_match_evidence_refs: list[str] = []
                use_multi_round_debate = _use_multi_round_debate(plan)
                for first, second in _schedule_pairs(hypotheses, proximity_edges, matches, max_matches, reviews):
                    pair_reviews = _reviews_for_pair(reviews, first.id, second.id)
                    ranked_pair, match = (
                        ranking.compare_multi_round_debate(
                            goal,
                            first,
                            second,
                            reviews=pair_reviews,
                            rounds=2,
                            evidence_store=evidence_store if use_grounded_review else None,
                        )
                        if use_multi_round_debate
                        else ranking.compare_debate(
                            goal,
                            first,
                            second,
                            reviews=pair_reviews,
                            evidence_store=evidence_store if use_grounded_review else None,
                        )
                    )
                    match = _apply_match_feedback(match, ranking_feedback)
                    hypotheses = _replace_hypotheses(hypotheses, ranked_pair)
                    matches.append(match)
                    cycle_match_ids.append(match.id)
                    cycle_match_evidence_refs.extend(match.evidence_refs)
                task_retrievals = evidence_store.consume_retrieval_memory(
                    cycle=cycle,
                    agent="ranking",
                    task_id=_task.id,
                    reason="ranking pair evidence retrieval",
                )
                retrieval_memory.extend(task_retrievals)
                action = "multi_round_debate_pairwise_compare" if use_multi_round_debate else "debate_pairwise_compare"
                comparison_label = "multi-round debate" if use_multi_round_debate else "deterministic debate"
                notes = f"Ran {len(cycle_match_ids)} {comparison_label} matches."
                if ranking_feedback:
                    notes += f" Agent feedback: {'; '.join(ranking_feedback)}."
                agent_traces.append(
                    _build_agent_trace(
                        cycle=cycle,
                        agent="ranking",
                        action=action,
                        input_refs=[item.id for item in hypotheses],
                        output_refs=cycle_match_ids,
                        notes=notes,
                        evidence_refs=_unique_refs(cycle_match_evidence_refs),
                        task_id=_task.id,
                        llm_interactions=ranking.consume_llm_interactions(),
                        scratchpad=_trace_scratchpad(
                            [
                                f"comparison_label={comparison_label}",
                                f"match_count={len(cycle_match_ids)}",
                            ],
                            task_retrievals,
                        ),
                        tool_calls=_tool_calls_from_retrievals(task_retrievals),
                    )
                )
                return cycle_match_ids

            ranking_task = schedule_cycle_task(
                "ranking",
                {
                    "comparison_mode": (
                        "deterministic_multi_round_debate_judge"
                        if _use_multi_round_debate(plan)
                        else "deterministic_debate_judge"
                    ),
                    "hypothesis_ids": [item.id for item in hypotheses],
                    "agent_feedback": ranking_feedback,
                },
                execute_ranking,
            )
            run_ready_cycle_tasks({proximity_task.id, ranking_task.id})

            leaders = _select_diverse_evolution_leaders(hypotheses, proximity_edges, limit=2)
            child_limit = min(2, max(max_hypotheses - len(hypotheses), 0))
            evolution_strategy = _active_evolution_strategy(plan, cycle, use_grounded=use_grounded_review)
            evolution_task: Task | None = None
            if leaders and child_limit:
                def execute_evolution(_task: Task) -> list[str]:
                    nonlocal hypotheses, proximity_edges
                    if evolution_strategy == "simplification":
                        children = evolution.evolve(
                            goal,
                            leaders,
                            evolution_feedback,
                            limit=child_limit,
                            evidence_store=evidence_store if use_grounded_review else None,
                        )
                    else:
                        children = evolution.evolve_with_strategy(
                            goal,
                            leaders,
                            evolution_feedback,
                            strategy=evolution_strategy,
                            limit=child_limit,
                            evidence_store=evidence_store if use_grounded_review else None,
                        )
                    task_retrievals = evidence_store.consume_retrieval_memory(
                        cycle=cycle,
                        agent="evolution",
                        task_id=_task.id,
                        reason=f"{evolution_strategy} evolution retrieval",
                    )
                    retrieval_memory.extend(task_retrievals)
                    evolution_notes = f"Evolved {len(children)} child hypotheses from current leaders."
                    if evolution_feedback:
                        evolution_notes += f" Agent feedback: {'; '.join(evolution_feedback)}."
                    agent_traces.append(
                        _build_agent_trace(
                            cycle=cycle,
                            agent="evolution",
                            action=evolution_strategy,
                            input_refs=[item.id for item in leaders],
                            output_refs=[item.id for item in children],
                            notes=evolution_notes,
                            evidence_refs=_evidence_refs_for_hypotheses(children),
                            task_id=_task.id,
                            llm_interactions=evolution.consume_llm_interactions(),
                            scratchpad=_trace_scratchpad(
                                [
                                    f"strategy={evolution_strategy}",
                                    f"leader_count={len(leaders)}",
                                    f"child_count={len(children)}",
                                ],
                                task_retrievals,
                            ),
                            tool_calls=_tool_calls_from_retrievals(task_retrievals),
                        )
                    )
                    child_reviews = _review_for_plan(
                        reflection=reflection,
                        goal=goal,
                        plan=plan,
                        hypotheses=children,
                        evidence_store=evidence_store,
                        use_grounded=use_grounded_review,
                        cycle=cycle,
                        agent_traces=agent_traces,
                        task_id=_task.id,
                        retrieval_memory=retrieval_memory,
                    )
                    accepted_child_ids = _accepted_hypothesis_ids(children, child_reviews)
                    hypotheses = _merge_hypotheses(
                        hypotheses,
                        [item.with_status("accepted") for item in children if item.id in accepted_child_ids],
                    )
                    reviews.extend(child_reviews)
                    proximity_edges = proximity.compute_goal_aware(goal, hypotheses, reviews, evidence_store)
                    proximity_edges = _apply_proximity_feedback(proximity_edges, proximity_feedback)
                    hypotheses = _apply_proximity_deduplication(hypotheses, proximity_edges)
                    return [item.id for item in children]

                evolution_task = schedule_cycle_task(
                    "evolution",
                    {
                        "strategy": evolution_strategy,
                        "leader_ids": [item.id for item in leaders],
                        "agent_feedback": evolution_feedback,
                    },
                    execute_evolution,
                )

            top_hypothesis_ids = [
                item.id
                for item in sorted(_active_hypotheses(hypotheses), key=lambda hyp: hyp.elo, reverse=True)[:3]
            ]

            def execute_meta_review(_task: Task) -> list[str]:
                nonlocal feedback
                meta = meta_review.summarize(
                    goal,
                    reviews,
                    matches,
                    evidence_store=evidence_store if use_grounded_review else None,
                )
                task_retrievals = evidence_store.consume_retrieval_memory(
                    cycle=cycle,
                    agent="meta_review",
                    task_id=_task.id,
                    reason="meta-review evidence retrieval",
                )
                retrieval_memory.extend(task_retrievals)
                metas.append(meta)
                feedback = meta.prompt_feedback
                agent_traces.append(
                    _build_agent_trace(
                        cycle=cycle,
                        agent="meta_review",
                        action="summarize",
                        input_refs=[item.id for item in reviews] + [item.id for item in matches],
                        output_refs=[meta.id],
                        notes=f"Summarized {len(reviews)} reviews and {len(matches)} matches.",
                        evidence_refs=meta.evidence_refs,
                        task_id=_task.id,
                        llm_interactions=meta_review.consume_llm_interactions(),
                        scratchpad=_trace_scratchpad(
                            [
                                f"review_count={len(reviews)}",
                                f"match_count={len(matches)}",
                            ],
                            task_retrievals,
                        ),
                        tool_calls=_tool_calls_from_retrievals(task_retrievals),
                    )
                )
                return [meta.id]

            meta_review_task = schedule_cycle_task(
                "meta_review",
                {
                    "review_count": len(reviews),
                    "match_count": len(matches),
                    "top_hypothesis_ids": top_hypothesis_ids,
                },
                execute_meta_review,
            )
            ready_meta_ids = {meta_review_task.id}
            if evolution_task is not None:
                ready_meta_ids.add(evolution_task.id)
            run_ready_cycle_tasks(ready_meta_ids)
            top_hypothesis_ids = [
                item.id
                for item in sorted(_active_hypotheses(hypotheses), key=lambda hyp: hyp.elo, reverse=True)[:3]
            ]

            def execute_overview(_task: Task) -> list[str]:
                nonlocal research_overview
                meta = metas[-1]
                research_overview = meta_review.build_overview(
                    goal, _active_hypotheses(hypotheses), metas, cycle=cycle
                )
                research_overview = _apply_overview_feedback(research_overview, overview_feedback)
                task_retrievals = evidence_store.consume_retrieval_memory(
                    cycle=cycle,
                    agent="overview",
                    task_id=_task.id,
                    reason="overview evidence retrieval",
                )
                retrieval_memory.extend(task_retrievals)
                overview_notes = "Rendered first-class research overview for human review."
                if overview_feedback:
                    overview_notes += f" Agent feedback: {'; '.join(overview_feedback)}."
                agent_traces.append(
                    _build_agent_trace(
                        cycle=cycle,
                        agent="overview",
                        action="render_research_overview",
                        input_refs=[meta.id, *research_overview.top_hypothesis_ids],
                        output_refs=[research_overview.id],
                        notes=overview_notes,
                        task_id=_task.id,
                        llm_interactions=meta_review.consume_llm_interactions(),
                        scratchpad=_trace_scratchpad(
                            [
                                f"top_hypothesis_count={len(research_overview.top_hypothesis_ids)}",
                                f"promising_direction_count={len(research_overview.promising_directions)}",
                            ],
                            task_retrievals,
                        ),
                        tool_calls=_tool_calls_from_retrievals(task_retrievals),
                    )
                )
                return [research_overview.id]

            run_cycle_task(
                "overview",
                {
                    "generated_by": "meta_review",
                    "top_hypothesis_ids": top_hypothesis_ids,
                    "agent_feedback": overview_feedback,
                },
                execute_overview,
            )

            def execute_research_outputs(_task: Task) -> list[str]:
                nonlocal research_output_artifacts
                cycle_outputs = meta_review.build_research_output_artifacts(
                    goal,
                    _active_hypotheses(hypotheses),
                    metas,
                    research_overview,
                    cycle=cycle,
                )
                task_retrievals = evidence_store.consume_retrieval_memory(
                    cycle=cycle,
                    agent="research_outputs",
                    task_id=_task.id,
                    reason="research output artifact retrieval",
                )
                retrieval_memory.extend(task_retrievals)
                research_output_artifacts = _merge_research_output_artifacts(
                    research_output_artifacts,
                    cycle_outputs,
                )
                agent_traces.append(
                    _build_agent_trace(
                        cycle=cycle,
                        agent="research_outputs",
                        action="render_publication_grant_contact_artifacts",
                        input_refs=[
                            *(item.id for item in metas[-1:]),
                            *(research_overview.top_hypothesis_ids if research_overview else []),
                        ],
                        output_refs=[item.id for item in cycle_outputs],
                        notes=(
                            "Rendered publication brief, grant brief, and contact suggestions "
                            "for human review."
                        ),
                        evidence_refs=_unique_refs([ref for item in cycle_outputs for ref in item.evidence_refs]),
                        task_id=_task.id,
                        llm_interactions=meta_review.consume_llm_interactions(),
                        scratchpad=_trace_scratchpad(
                            [
                                f"artifact_count={len(cycle_outputs)}",
                                "output_types=publication_brief,grant_brief,contact_suggestions",
                            ],
                            task_retrievals,
                        ),
                        tool_calls=_tool_calls_from_retrievals(task_retrievals),
                    )
                )
                return [item.id for item in cycle_outputs]

            run_cycle_task(
                "research_outputs",
                {
                    "generated_by": "meta_review",
                    "top_hypothesis_ids": top_hypothesis_ids,
                    "output_types": ["publication_brief", "grant_brief", "contact_suggestions"],
                },
                execute_research_outputs,
            )

            feedback_evaluation = _build_feedback_loop_evaluation(
                cycle=cycle,
                source_meta=source_feedback_meta,
                baseline_quality=baseline_feedback_quality,
                hypotheses=hypotheses,
                reviews=reviews,
                matches=matches,
                proximity_edges=proximity_edges,
                research_overview=research_overview,
                agent_traces=agent_traces,
            )
            if feedback_evaluation:
                feedback_loop_evaluations = _merge_feedback_loop_evaluations(
                    feedback_loop_evaluations,
                    [feedback_evaluation],
                )

            context_snapshots.append(
                _build_context_snapshot(
                    cycle=cycle,
                    plan=plan,
                    hypotheses=hypotheses,
                    reviews=reviews,
                    matches=matches,
                    meta_review_count=len(metas),
                    proximity_edges=proximity_edges,
                    max_hypotheses=max_hypotheses,
                )
            )
            termination_reason = evaluate_termination_criteria(
                plan, hypotheses, reviews, context_snapshots
            )
            if termination_reason:
                context_snapshots[-1] = replace(
                    context_snapshots[-1], termination_reason=termination_reason
                )
                state = current_state(run_status, task_queue)
                _write_state(state_path, state)
                break
            state = current_state(run_status, task_queue)
            _write_state(state_path, state)
    except _TaskDeferred as deferred:
        state = current_state(deferred.run_status, task_queue)
        _write_state(state_path, state)
        return state

    final_hypotheses = sorted(hypotheses, key=lambda item: item.elo, reverse=True)
    capability_evaluations = _merge_capability_evaluations(
        capability_evaluations,
        load_capability_evaluation_fixtures(capability_evaluation_paths or [], goal, final_hypotheses),
    )
    state = RunState(
        goal=goal,
        run_status=run_status,
        plan=plan,
        evidence=state.evidence,
        evidence_safety_findings=evidence_safety_findings,
        hypotheses=final_hypotheses,
        reviews=reviews,
        matches=matches,
        proximity_edges=proximity_edges,
        benchmark_results=benchmarks,
        capability_evaluations=capability_evaluations,
        prospective_evaluations=prospective_evaluations,
        scaling_curve=scaling_curve,
        safety_evaluations=safety_evaluations,
        feedback_loop_evaluations=feedback_loop_evaluations,
        research_output_artifacts=research_output_artifacts,
        meta_reviews=metas,
        context_snapshots=context_snapshots,
        safety=safety,
        research_overview=research_overview,
        user_feedback=user_feedback,
        agent_traces=agent_traces,
        retrieval_memory=retrieval_memory,
        task_queue=task_queue,
    )
    _write_state(state_path, state)
    return state


def run_continuous_research(
    objective: str,
    max_hypotheses: int,
    max_matches: int,
    out_dir: str | Path,
    provider: str = "deterministic",
    model: str | None = None,
    max_tokens: int = 1024,
    env_file: str | Path = ".env",
    llm_client: Any | None = None,
    goal_brief_paths: list[str | Path] | None = None,
    safety_policy_paths: list[str | Path] | None = None,
    benchmark_results: list[BenchmarkResult] | None = None,
    evidence_paths: list[str | Path] | None = None,
    evidence_index_paths: list[str | Path] | None = None,
    repo_search_paths: list[str | Path] | None = None,
    web_evidence_urls: list[str] | None = None,
    web_crawl_depth: int = 0,
    web_search_queries: list[str] | None = None,
    web_search_fetch: bool = False,
    web_search_crawl_depth: int = 0,
    literature_search_queries: list[str] | None = None,
    literature_full_text: bool = False,
    capability_evaluation_paths: list[str | Path] | None = None,
    interval_seconds: float = 60,
    max_wall_minutes: float | None = None,
    max_continuous_cycles: int | None = None,
    after_cycle: Callable[[RunState], None] | None = None,
) -> RunState:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    state_path = out_path / "state.json"
    control_path = out_path / "control.json"
    started = time.monotonic()
    completed_cycles = 0
    model_client = _build_model_client(
        provider=provider,
        model=model,
        env_file=env_file,
        llm_client=llm_client,
    )
    state = _ensure_continuous_state(
        objective=objective,
        out_path=out_path,
        benchmark_results=benchmark_results,
        goal_brief_paths=goal_brief_paths,
        safety_policy_paths=safety_policy_paths,
        evidence_paths=evidence_paths,
        evidence_index_paths=evidence_index_paths,
        repo_search_paths=repo_search_paths,
        web_evidence_urls=web_evidence_urls,
        web_crawl_depth=web_crawl_depth,
        web_search_queries=web_search_queries,
        web_search_fetch=web_search_fetch,
        web_search_crawl_depth=web_search_crawl_depth,
        literature_search_queries=literature_search_queries,
        literature_full_text=literature_full_text,
        safety_llm_client=model_client if provider == "anthropic" else None,
        max_tokens=max_tokens,
    )

    while True:
        action = _read_control_action(control_path)
        if action == "stop":
            return _set_run_status(state_path, "stopped")
        if _exceeded_wall_time(started, max_wall_minutes):
            return _set_run_status(state_path, "completed")
        if max_continuous_cycles is not None and completed_cycles >= max_continuous_cycles:
            return _set_run_status(state_path, "completed")
        if action == "pause":
            state = _set_run_status(state_path, "paused")
            time.sleep(_sleep_interval(interval_seconds))
            continue

        state = run_research_cycle(
            objective=objective,
            cycles=1,
            max_hypotheses=max_hypotheses,
            max_matches=max_matches,
            out_dir=out_path,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            env_file=env_file,
            llm_client=llm_client,
            benchmark_results=benchmark_results,
            goal_brief_paths=goal_brief_paths,
            safety_policy_paths=safety_policy_paths,
            evidence_paths=evidence_paths,
            evidence_index_paths=evidence_index_paths,
            repo_search_paths=repo_search_paths,
            web_evidence_urls=web_evidence_urls,
            web_crawl_depth=web_crawl_depth,
            web_search_queries=web_search_queries,
            web_search_fetch=web_search_fetch,
            web_search_crawl_depth=web_search_crawl_depth,
            literature_search_queries=literature_search_queries,
            literature_full_text=literature_full_text,
            capability_evaluation_paths=capability_evaluation_paths,
            resume=True,
            run_status="running",
            control_path=control_path,
        )
        if state.run_status == "stopped":
            return state
        if state.run_status == "paused":
            time.sleep(_sleep_interval(interval_seconds))
            continue
        completed_cycles += 1
        if after_cycle:
            after_cycle(state)

        if state.context_snapshots and state.context_snapshots[-1].termination_reason:
            return _set_run_status(state_path, "completed")

        action = _read_control_action(control_path)
        if action == "stop":
            return _set_run_status(state_path, "stopped")
        if max_continuous_cycles is not None and completed_cycles >= max_continuous_cycles:
            return _set_run_status(state_path, "completed")
        if _exceeded_wall_time(started, max_wall_minutes):
            return _set_run_status(state_path, "completed")
        time.sleep(interval_seconds)


def load_state(path: str | Path) -> RunState:
    return RunState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _read_goal_briefs(paths: list[str | Path]) -> list[str]:
    return [read_document_text(path) for path in paths]


def _goal_safety_text(goal: ResearchGoal) -> str:
    sections = [
        ("Objective", [goal.objective]),
        ("Preferences", goal.preferences),
        ("Constraints", goal.constraints),
        ("Metrics", goal.metrics),
        ("Safety notes", goal.safety_notes),
        ("Allowed sources", goal.allowed_sources),
        ("Allowed tools", goal.allowed_tools),
        ("Output formats", goal.output_formats),
        ("Termination criteria", goal.termination_criteria),
    ]
    return "\n".join(
        f"{label}: {'; '.join(value for value in values if value)}"
        for label, values in sections
        if any(values)
    )


def _write_state(path: Path, state: RunState) -> None:
    _write_agent_transcripts(path.parent, state)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _write_agent_transcripts(run_dir: Path, state: RunState) -> None:
    run_root = run_dir.resolve()
    evidence_ids = {item.id for item in state.evidence}
    for trace in state.agent_traces:
        if not trace.transcript_ref or not trace.llm_interactions:
            continue
        transcript_path = (run_root / trace.transcript_ref).resolve()
        if not transcript_path.is_relative_to(run_root):
            raise ValueError(f"Agent transcript path escapes run directory: {trace.transcript_ref}")
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        unresolved_refs = [ref for ref in trace.evidence_refs if ref not in evidence_ids]
        citation_status = (
            "unresolved"
            if unresolved_refs
            else "resolved"
            if trace.evidence_refs
            else "not_applicable"
        )
        records = [
            {
                "trace_id": trace.id,
                "cycle": trace.cycle,
                "agent": trace.agent,
                "action": trace.action,
                "task_id": trace.task_id,
                "turn_index": index,
                "turn": interaction.get("turn", ""),
                "prompt": interaction.get("prompt", ""),
                "response": interaction.get("response", ""),
                "max_tokens": interaction.get("max_tokens", ""),
                "tool_calls": [
                    _llm_complete_tool_call(trace, interaction, index),
                    *trace.tool_calls,
                ],
                "evidence_refs": trace.evidence_refs,
                "citation_check": {
                    "status": citation_status,
                    "unresolved_evidence_refs": unresolved_refs,
                },
            }
            for index, interaction in enumerate(trace.llm_interactions, start=1)
        ]
        transcript_path.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
            encoding="utf-8",
        )


def _collect_plan_governed_evidence(
    *,
    goal: ResearchGoal,
    plan: ResearchPlanConfig,
    evidence_paths: list[str | Path],
    evidence_index_paths: list[str | Path],
    repo_search_paths: list[str | Path],
    web_evidence_urls: list[str],
    web_crawl_depth: int,
    web_search_queries: list[str],
    web_search_fetch: bool,
    web_search_crawl_depth: int,
    literature_search_queries: list[str],
    literature_full_text: bool,
    safety_policies: list[SafetyPolicy] | None = None,
) -> tuple[list[Evidence], list[EvidenceSafetyFinding]]:
    evidence: list[Evidence] = []
    findings: list[EvidenceSafetyFinding] = []

    if evidence_paths:
        evidence.extend(EvidenceStore.from_paths(evidence_paths).evidence)

    if evidence_index_paths:
        if _plan_allows_source_request(
            plan,
            ("evidence_index", "indexed_corpus", "private_corpus", "local_embedding"),
            ("evidence_index", "private_corpus_retrieval"),
        ):
            evidence.extend(EvidenceStore.from_indexes(evidence_index_paths).evidence)
        else:
            findings.append(_source_policy_finding("evidence_index", evidence_index_paths, plan))

    if repo_search_paths:
        if _plan_allows_source_request(
            plan,
            ("repo_search", "local_repo_search", "repository", "local_repository", "local"),
            ("repo_search", "local_repo_search", "repository_search"),
        ):
            evidence.extend(collect_local_repo_search_evidence(goal.objective, repo_search_paths))
        else:
            findings.append(_source_policy_finding("repo_search", repo_search_paths, plan))

    if web_evidence_urls:
        if _plan_allows_source_request(
            plan,
            ("web_evidence", "web_document", "web_url", "url", "web"),
            ("web_fetch", "web_evidence", "http_fetch"),
        ):
            evidence.extend(collect_web_evidence(web_evidence_urls, crawl_depth=web_crawl_depth))
        else:
            findings.append(_source_policy_finding("web_evidence", web_evidence_urls, plan))

    if web_search_queries:
        if _plan_allows_source_request(
            plan,
            ("web_search", "web_search_result", "web", "search"),
            ("web_search",),
        ):
            evidence.extend(
                collect_web_search_evidence(
                    web_search_queries,
                    fetch_documents=web_search_fetch,
                    fetch_crawl_depth=web_search_crawl_depth,
                )
            )
        else:
            findings.append(_source_policy_finding("web_search", web_search_queries, plan))

    if literature_search_queries:
        if _plan_allows_source_request(
            plan,
            ("literature", "literature_search", "openalex", "publication", "full_text"),
            ("literature_search", "openalex_literature_search", "openalex"),
        ):
            evidence.extend(
                collect_literature_search_evidence(
                    literature_search_queries,
                    include_full_text=literature_full_text,
                    safety_policies=safety_policies,
                )
            )
        else:
            findings.append(_source_policy_finding("literature_search", literature_search_queries, plan))

    return evidence, findings


def _plan_allows_source_request(
    plan: ResearchPlanConfig,
    source_aliases: tuple[str, ...],
    tool_aliases: tuple[str, ...] = (),
) -> bool:
    source_values = _active_source_policy_values(plan.allowed_sources)
    tool_values = _active_tool_policy_values(plan.allowed_tools)
    if not source_values and not tool_values:
        return True
    source_ok = not source_values or _matches_any_policy_alias(source_values, source_aliases)
    tool_ok = not tool_values or not tool_aliases or _matches_any_policy_alias(tool_values, tool_aliases)
    return source_ok and tool_ok


def _active_source_policy_values(values: list[str]) -> list[str]:
    normalized = [_normalize_policy_value(value) for value in values if value.strip()]
    default_sources = {"seed_paper_evidence", "local_evidence_paths"}
    if set(normalized) <= default_sources:
        return []
    return normalized


def _active_tool_policy_values(values: list[str]) -> list[str]:
    normalized = [_normalize_policy_value(value) for value in values if value.strip()]
    default_tools = {"deterministic_agents", "deterministic_agent"}
    if set(normalized) <= default_tools:
        return []
    return normalized


def _matches_any_policy_alias(values: list[str], aliases: tuple[str, ...]) -> bool:
    normalized_aliases = [_normalize_policy_value(alias) for alias in aliases]
    return any(
        alias == value or alias in value or value in alias
        for value in values
        for alias in normalized_aliases
    )


def _normalize_policy_value(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _source_policy_finding(
    source_id: str,
    requested: list[str | Path],
    plan: ResearchPlanConfig,
) -> EvidenceSafetyFinding:
    requested_text = ", ".join(str(item) for item in requested[:5])
    reason = (
        f"{source_id} evidence was requested but is not allowed by the research plan. "
        f"Allowed sources: {', '.join(plan.allowed_sources) or 'none'}; "
        f"allowed tools: {', '.join(plan.allowed_tools) or 'none'}."
    )
    return EvidenceSafetyFinding(
        id=stable_id("evsafe", f"source_policy:{source_id}:{requested_text}:{reason}"),
        evidence_id=f"source_policy:{source_id}",
        source=source_id,
        allowed=False,
        flags=[f"source-policy:{source_id}"],
        reason=reason,
        content_preview=requested_text,
    )


def _ensure_continuous_state(
    objective: str,
    out_path: Path,
    benchmark_results: list[BenchmarkResult] | None,
    goal_brief_paths: list[str | Path] | None = None,
    safety_policy_paths: list[str | Path] | None = None,
    evidence_paths: list[str | Path] | None = None,
    evidence_index_paths: list[str | Path] | None = None,
    repo_search_paths: list[str | Path] | None = None,
    web_evidence_urls: list[str] | None = None,
    web_crawl_depth: int = 0,
    web_search_queries: list[str] | None = None,
    web_search_fetch: bool = False,
    web_search_crawl_depth: int = 0,
    literature_search_queries: list[str] | None = None,
    literature_full_text: bool = False,
    safety_llm_client: Any | None = None,
    max_tokens: int = 1024,
) -> RunState:
    state_path = out_path / "state.json"
    if state_path.exists():
        state = replace(load_state(state_path), run_status="running")
        _write_state(state_path, state)
        return state

    goal = ResearchGoal.from_objective_with_briefs(objective, _read_goal_briefs(goal_brief_paths or []))
    plan = ResearchPlanConfig.from_goal(goal)
    safety_policies = load_safety_policies(safety_policy_paths or [])
    safety_fail_closed = any(policy.fail_closed for policy in safety_policies)
    seed_evidence = seed_paper_evidence()
    initial_state = RunState(
        goal=goal,
        run_status="running",
        plan=plan,
        evidence=seed_evidence,
        benchmark_results=benchmark_results or [],
    )
    _write_state(state_path, initial_state)
    governed_evidence, governance_findings = _collect_plan_governed_evidence(
        goal=goal,
        plan=plan,
        evidence_paths=evidence_paths or [],
        evidence_index_paths=evidence_index_paths or [],
        repo_search_paths=repo_search_paths or [],
        web_evidence_urls=web_evidence_urls or [],
        web_crawl_depth=web_crawl_depth,
        web_search_queries=web_search_queries or [],
        web_search_fetch=web_search_fetch,
        web_search_crawl_depth=web_search_crawl_depth,
        literature_search_queries=literature_search_queries or [],
        literature_full_text=literature_full_text,
        safety_policies=safety_policies,
    )
    merged_evidence = merge_evidence(
        seed_evidence,
        governed_evidence,
    )
    evidence, evidence_safety_findings = screen_evidence_sources(
        merged_evidence,
        llm_client=safety_llm_client,
        max_tokens=max_tokens,
        safety_policies=safety_policies,
        fail_closed=safety_fail_closed,
    )
    state = replace(
        initial_state,
        evidence=evidence,
        evidence_safety_findings=_merge_evidence_safety_findings(governance_findings, evidence_safety_findings),
        safety=review_goal_safety_with_model(
            _goal_safety_text(goal),
            safety_llm_client,
            max_tokens=max_tokens,
            safety_policies=safety_policies,
            fail_closed=safety_fail_closed,
        ),
    )
    _write_state(state_path, state)
    return state


def _set_run_status(state_path: Path, status: str) -> RunState:
    state = replace(load_state(state_path), run_status=status)
    _write_state(state_path, state)
    return state


def _merge_evidence_safety_findings(
    existing: list[EvidenceSafetyFinding],
    *additions: list[EvidenceSafetyFinding],
) -> list[EvidenceSafetyFinding]:
    by_id = {item.id: item for item in existing}
    for group in additions:
        for item in group:
            by_id.setdefault(item.id, item)
    return list(by_id.values())


def _merge_capability_evaluations(
    existing: list[Any],
    additions: list[Any],
) -> list[Any]:
    by_id = {item.id: item for item in existing}
    for item in additions:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def _merge_feedback_loop_evaluations(
    existing: list[FeedbackLoopEvaluation],
    additions: list[FeedbackLoopEvaluation],
) -> list[FeedbackLoopEvaluation]:
    by_id = {item.id: item for item in existing}
    for item in additions:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def _merge_research_output_artifacts(
    existing: list[ResearchOutputArtifact],
    additions: list[ResearchOutputArtifact],
) -> list[ResearchOutputArtifact]:
    by_id = {item.id: item for item in existing}
    for item in additions:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def _agent_feedback_for(metas: list[MetaReview], agent: str) -> list[str]:
    if not metas:
        return []
    latest = metas[-1].agent_feedback or {}
    return _unique_refs([
        *latest.get(agent, []),
        *latest.get("all", []),
        *latest.get("*", []),
    ])


def _read_control_action(control_path: Path) -> str:
    if not control_path.exists():
        return "run"
    try:
        data = json.loads(control_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "run"
    action = str(data.get("action", "run")).lower()
    return action if action in {"run", "pause", "stop"} else "run"


def _exceeded_wall_time(started: float, max_wall_minutes: float | None) -> bool:
    if max_wall_minutes is None:
        return False
    return time.monotonic() - started >= max_wall_minutes * 60


def _sleep_interval(interval_seconds: float) -> float:
    return interval_seconds if interval_seconds > 0 else 0.05


class _TaskDeferred(Exception):
    def __init__(self, run_status: str) -> None:
        super().__init__(run_status)
        self.run_status = run_status


def _build_model_client(
    provider: str,
    model: str | None,
    env_file: str | Path,
    llm_client: Any | None,
) -> Any | None:
    if provider == "deterministic":
        return None
    if provider == "anthropic":
        return llm_client or AnthropicHaikuClient.from_environment(
            model=model or DEFAULT_ANTHROPIC_MODEL,
            env_path=env_file,
        )
    raise ValueError(f"Unknown provider: {provider}")


def _plan_for_goal(
    goal: ResearchGoal,
    provider: str,
    model_client: Any | None,
    max_tokens: int,
) -> ResearchPlanConfig:
    if provider == "anthropic" and model_client is not None:
        try:
            return parse_research_plan_with_llm(goal, model_client, max_tokens=max_tokens)
        except LLMResponseError:
            pass
    return ResearchPlanConfig.from_goal(goal)


def _build_generation_agent(
    provider: str,
    model: str | None,
    max_tokens: int,
    env_file: str | Path,
    llm_client: Any | None,
) -> GenerationAgent:
    if provider == "deterministic":
        return GenerationAgent()
    if provider == "anthropic":
        client = llm_client or _build_model_client(provider, model, env_file, llm_client)
        return GenerationAgent(llm_client=client, llm_max_tokens=max_tokens, llm_origin="anthropic-haiku")
    raise ValueError(f"Unknown provider: {provider}")


def _generate_for_plan(
    generation: GenerationAgent,
    goal: ResearchGoal,
    plan: ResearchPlanConfig,
    evidence: list[Any],
    evidence_store: EvidenceStore,
    limit: int,
    use_grounded: bool,
    cycle: int,
    agent_traces: list[AgentTrace],
    agent_feedback: list[str] | None = None,
    task_id: str = "",
    existing_hypotheses: list[Hypothesis] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
    generation_allocations: list[dict[str, Any]] | None = None,
    retrieval_memory: list[RetrievalMemoryRecord] | None = None,
) -> list[Hypothesis]:
    if limit <= 0:
        return []
    modes = _active_generation_methods(plan, use_grounded)
    allocations = generation_allocations or _allocate_generation_methods(
        modes,
        limit,
        hypotheses=existing_hypotheses or [],
        proximity_edges=proximity_edges or [],
    )
    generated: list[Hypothesis] = []
    existing_ids: set[str] = set()
    for index, allocation in enumerate(allocations):
        mode = str(allocation.get("mode", "")).strip()
        if mode not in modes:
            continue
        remaining = limit - len(generated)
        if remaining <= 0:
            break
        later_reserved = sum(_allocation_limit(item) for item in allocations[index + 1 :])
        requested_limit = _allocation_limit(allocation)
        mode_limit = min(remaining, max(requested_limit, remaining - later_reserved))
        source = (
            evidence_store
            if use_grounded or mode in {"literature_grounded_generation", "tool_augmented_generation"}
            else evidence
        )
        mode_items = generation.generate_with_mode(goal, source, mode=mode, limit=mode_limit)
        mode_retrievals = evidence_store.consume_retrieval_memory(
            cycle=cycle,
            agent="generation",
            task_id=task_id,
            reason=f"{mode} evidence retrieval",
        )
        if retrieval_memory is not None:
            retrieval_memory.extend(mode_retrievals)
        mode_items = _apply_generation_feedback(goal, mode_items, mode, agent_feedback or [])
        unique_mode_items = [item for item in mode_items if item.id not in existing_ids]
        for item in unique_mode_items:
            existing_ids.add(item.id)
        generated.extend(unique_mode_items)
        allocation_reason = str(allocation.get("reason", "")).strip()
        notes = f"Generated {len(unique_mode_items)} hypotheses with {mode}; allocated {mode_limit} slot(s)."
        if allocation_reason:
            notes += f" Allocation reason: {allocation_reason}."
        if agent_feedback:
            notes += f" Agent feedback: {'; '.join(agent_feedback)}."
        agent_traces.append(
            _build_agent_trace(
                cycle=cycle,
                agent="generation",
                action=mode,
                input_refs=[goal.id, *(item.id for item in evidence[:5])],
                output_refs=[item.id for item in unique_mode_items],
                notes=notes,
                evidence_refs=_evidence_refs_for_hypotheses(unique_mode_items),
                task_id=task_id,
                llm_interactions=generation.consume_llm_interactions(),
                scratchpad=_trace_scratchpad(
                    [
                        f"mode={mode}",
                        f"allocated_slots={mode_limit}",
                        f"generated={len(unique_mode_items)}",
                    ],
                    mode_retrievals,
                ),
                tool_calls=_tool_calls_from_retrievals(mode_retrievals),
            )
        )
    return generated[:limit]


def _apply_generation_feedback(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    mode: str,
    agent_feedback: list[str],
) -> list[Hypothesis]:
    if not agent_feedback:
        return hypotheses
    feedback_text = "; ".join(agent_feedback)
    return [
        replace(
            item,
            id=stable_id("hyp", f"{goal.id}:{mode}:agent-feedback:{item.id}:{feedback_text}"),
            rationale=f"{item.rationale} Meta-review feedback for generation: {feedback_text}.",
            assumptions=_unique_refs([
                *item.assumptions,
                "Generation incorporated targeted meta-review feedback.",
            ]),
        )
        for item in hypotheses
    ]


def _review_for_plan(
    reflection: ReflectionAgent,
    goal: ResearchGoal,
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis],
    evidence_store: EvidenceStore,
    use_grounded: bool,
    cycle: int,
    agent_traces: list[AgentTrace],
    agent_feedback: list[str] | None = None,
    safety_feedback: list[str] | None = None,
    task_id: str = "",
    retrieval_memory: list[RetrievalMemoryRecord] | None = None,
) -> list[Review]:
    reviews: list[Review] = []
    for review_type in _active_review_types(plan, use_grounded):
        mode_reviews = [
            reflection.review_with_type(
                goal,
                item,
                review_type,
                evidence_store if use_grounded else None,
            )
            for item in hypotheses
        ]
        mode_retrievals = evidence_store.consume_retrieval_memory(
            cycle=cycle,
            agent="reflection",
            task_id=task_id,
            reason=f"{review_type} evidence retrieval",
        )
        if retrieval_memory is not None:
            retrieval_memory.extend(mode_retrievals)
        mode_reviews = _apply_review_feedback(mode_reviews, agent_feedback or [], "reflection")
        if review_type == "safety_review":
            mode_reviews = _apply_review_feedback(mode_reviews, safety_feedback or [], "safety")
        reviews.extend(mode_reviews)
        notes = f"Ran {review_type} for {len(mode_reviews)} hypotheses."
        if agent_feedback:
            notes += f" Agent feedback: {'; '.join(agent_feedback)}."
        if review_type == "safety_review" and safety_feedback:
            notes += f" Safety feedback: {'; '.join(safety_feedback)}."
        agent_traces.append(
            _build_agent_trace(
                cycle=cycle,
                agent="reflection",
                action=review_type,
                input_refs=[item.id for item in hypotheses],
                output_refs=[item.id for item in mode_reviews],
                notes=notes,
                evidence_refs=sorted({ref for review in mode_reviews for ref in review.evidence_refs}),
                task_id=task_id,
                llm_interactions=reflection.consume_llm_interactions(),
                scratchpad=_trace_scratchpad(
                    [
                        f"review_type={review_type}",
                        f"hypothesis_count={len(hypotheses)}",
                        f"review_count={len(mode_reviews)}",
                    ],
                    mode_retrievals,
                ),
                tool_calls=_tool_calls_from_retrievals(mode_retrievals),
            )
        )
    return reviews


def _apply_review_feedback(reviews: list[Review], agent_feedback: list[str], agent: str) -> list[Review]:
    if not agent_feedback:
        return reviews
    feedback_text = "; ".join(agent_feedback)
    return [
        replace(
            review,
            findings=_unique_refs([
                *review.findings,
                f"Meta-review feedback for {agent}: {feedback_text}.",
            ]),
        )
        for review in reviews
    ]


def _apply_match_feedback(match: Match, agent_feedback: list[str]) -> Match:
    if not agent_feedback:
        return match
    feedback_text = "; ".join(agent_feedback)
    feedback_note = f"Meta-review feedback for ranking: {feedback_text}."
    judge_trace = f"{match.judge_trace} {feedback_note}".strip()
    return replace(
        match,
        judge_trace=judge_trace,
        debate_transcript=_unique_refs([*match.debate_transcript, feedback_note]),
    )


def _apply_proximity_feedback(edges: list[ProximityEdge], agent_feedback: list[str]) -> list[ProximityEdge]:
    if not agent_feedback:
        return edges
    feedback_text = "; ".join(agent_feedback)
    feedback_note = f"Meta-review feedback for proximity: {feedback_text}."
    return [
        replace(
            edge,
            reason=f"{edge.reason} {feedback_note}".strip(),
        )
        for edge in edges
    ]


def _apply_overview_feedback(overview: ResearchOverview, agent_feedback: list[str]) -> ResearchOverview:
    if not agent_feedback:
        return overview
    feedback_text = "; ".join(agent_feedback)
    feedback_note = f"Meta-review feedback for overview: {feedback_text}."
    return replace(
        overview,
        summary=f"{overview.summary} {feedback_note}",
        next_experiments=_unique_refs([*overview.next_experiments, feedback_note]),
        limitations=_unique_refs([*overview.limitations, feedback_note]),
    )


def _build_feedback_loop_evaluation(
    cycle: int,
    source_meta: MetaReview | None,
    baseline_quality: dict[str, float],
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    matches: list[Match],
    proximity_edges: list[ProximityEdge],
    research_overview: ResearchOverview | None,
    agent_traces: list[AgentTrace],
) -> FeedbackLoopEvaluation | None:
    feedback_items = _feedback_items(source_meta)
    if not source_meta or not feedback_items:
        return None
    artifact_text, artifact_refs = _feedback_artifact_text_and_refs(
        cycle=cycle,
        hypotheses=hypotheses,
        reviews=reviews,
        matches=matches,
        proximity_edges=proximity_edges,
        research_overview=research_overview,
        agent_traces=agent_traces,
    )
    adopted = [
        feedback
        for _agent, feedback in feedback_items
        if feedback.lower() in artifact_text.lower()
    ]
    observed_quality = _feedback_quality_metrics(hypotheses, reviews)
    deltas = {
        key: round(observed_quality.get(key, 0.0) - value, 3)
        for key, value in baseline_quality.items()
    }
    adopted_count = len(adopted)
    feedback_count = len(feedback_items)
    adoption_rate = round(adopted_count / feedback_count, 3) if feedback_count else 0.0
    agents = sorted({agent for agent, _feedback in feedback_items})
    summary = (
        f"{adopted_count}/{feedback_count} feedback items appeared in later artifacts; "
        "quality metrics are proxy counts, not external validation."
    )
    return FeedbackLoopEvaluation(
        id=stable_id(
            "feedback-loop",
            f"{source_meta.id}:{cycle}:{feedback_count}:{adopted_count}:{','.join(artifact_refs)}",
        ),
        cycle=cycle,
        source_meta_review_id=source_meta.id,
        feedback_agents=agents,
        feedback_item_count=feedback_count,
        adopted_feedback_count=adopted_count,
        adoption_rate=adoption_rate,
        baseline_quality=baseline_quality,
        observed_quality=observed_quality,
        deltas=deltas,
        artifact_refs=artifact_refs,
        summary=summary,
    )


def _feedback_items(meta: MetaReview | None) -> list[tuple[str, str]]:
    if not meta:
        return []
    items: list[tuple[str, str]] = []
    for agent, feedback_items in meta.agent_feedback.items():
        for feedback in feedback_items:
            if feedback:
                items.append((agent, feedback))
    return items


def _feedback_artifact_text_and_refs(
    cycle: int,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    matches: list[Match],
    proximity_edges: list[ProximityEdge],
    research_overview: ResearchOverview | None,
    agent_traces: list[AgentTrace],
) -> tuple[str, list[str]]:
    chunks: list[tuple[str, str]] = []
    for trace in agent_traces:
        if trace.cycle == cycle:
            chunks.append(
                (
                    trace.id,
                    " ".join([trace.agent, trace.action, trace.notes, *trace.input_refs, *trace.output_refs]),
                )
            )
    for hypothesis in hypotheses:
        chunks.append(
            (
                hypothesis.id,
                " ".join(
                    [
                        hypothesis.title,
                        hypothesis.claim,
                        hypothesis.rationale,
                        *hypothesis.assumptions,
                        *hypothesis.risks,
                    ]
                ),
            )
        )
    for review in reviews:
        chunks.append(
            (
                review.id,
                " ".join([review.review_type, *review.strengths, *review.weaknesses, *review.findings]),
            )
        )
    for match in matches:
        chunks.append((match.id, " ".join([match.rationale, match.judge_trace, *match.debate_transcript])))
    for edge in proximity_edges:
        chunks.append((_pair_key(edge.source, edge.target), edge.reason))
    if research_overview:
        chunks.append(
            (
                research_overview.id,
                " ".join(
                    [
                        research_overview.summary,
                        *research_overview.promising_directions,
                        *research_overview.next_experiments,
                        *research_overview.limitations,
                    ]
                ),
            )
        )
    artifact_text = "\n".join(text for _ref, text in chunks if text)
    artifact_refs = _unique_refs([ref for ref, text in chunks if text and "meta-review feedback" in text.lower()])
    if not artifact_refs:
        artifact_refs = _unique_refs([ref for ref, text in chunks if text])[:8]
    return artifact_text, artifact_refs[:16]


def _feedback_quality_metrics(hypotheses: list[Hypothesis], reviews: list[Review]) -> dict[str, float]:
    accepted = [item for item in hypotheses if item.status == "accepted"]
    review_count = len(reviews)
    return {
        "accepted_total": float(len(accepted)),
        "evidence_backed_hypotheses": float(len([item for item in accepted if item.evidence_refs])),
        "average_review_confidence": round(
            sum(review.confidence for review in reviews) / review_count,
            3,
        )
        if review_count
        else 0.0,
        "revision_rate": round(
            len([review for review in reviews if review.requires_revision]) / review_count,
            3,
        )
        if review_count
        else 0.0,
    }


def _active_generation_methods(plan: ResearchPlanConfig, use_grounded: bool) -> list[str]:
    methods = list(plan.generation_methods or ["paper_seeded_idea_generation"])
    if use_grounded and "literature_grounded_generation" not in methods:
        methods.append("literature_grounded_generation")
    if use_grounded and _plan_allows_external_tools(plan) and "tool_augmented_generation" not in methods:
        methods.append("tool_augmented_generation")
    return methods


def _allocate_generation_methods(
    modes: list[str],
    limit: int,
    hypotheses: list[Hypothesis] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    unique_modes = list(dict.fromkeys(mode for mode in modes if mode))
    if not unique_modes:
        return []

    active_counts: Counter[str] = Counter()
    merged_counts: Counter[str] = Counter()
    mode_by_hypothesis_id: dict[str, str] = {}
    cluster_ids_by_mode: dict[str, set[str]] = {mode: set() for mode in unique_modes}
    control_counts: Counter[str] = Counter()

    for hypothesis in hypotheses or []:
        # Cannot use _INACTIVE_STATUSES here: merged_duplicate is still counted in
        # allocation stats (as merged_counts) to gauge mode saturation, whereas a
        # quarantined hypothesis is unsafe and must not influence allocation at all.
        if hypothesis.status == "quarantined":
            continue
        mode = _generation_method_for_origin(hypothesis.origin, unique_modes)
        if not mode:
            continue
        mode_by_hypothesis_id[hypothesis.id] = mode
        if hypothesis.status == "merged_duplicate":
            merged_counts[mode] += 1
        else:
            active_counts[mode] += 1

    for edge in proximity_edges or []:
        incident_modes = {
            mode_by_hypothesis_id[item_id]
            for item_id in (edge.source, edge.target)
            if item_id in mode_by_hypothesis_id
        }
        if not incident_modes:
            continue
        for mode in incident_modes:
            if edge.cluster_id:
                cluster_ids_by_mode[mode].add(edge.cluster_id)
            if edge.deduplication_action or edge.diversity_action == "avoid_redundant_parallel_exploration":
                control_counts[mode] += 1

    def saturation_score(mode: str) -> tuple[float, int]:
        active = active_counts[mode]
        merged = merged_counts[mode]
        cluster_count = len(cluster_ids_by_mode[mode])
        controls = control_counts[mode]
        score = (10.0 * active) + (4.0 * merged) + (2.0 * cluster_count) + controls
        return score, unique_modes.index(mode)

    selected_modes = sorted(unique_modes, key=saturation_score)[: min(limit, len(unique_modes))]
    allocations = [
        {
            "mode": mode,
            "limit": 1,
            "reason": _generation_allocation_reason(
                mode,
                active_counts=active_counts,
                merged_counts=merged_counts,
                cluster_ids_by_mode=cluster_ids_by_mode,
                control_counts=control_counts,
            ),
        }
        for mode in selected_modes
    ]
    remaining = limit - len(allocations)
    allocation_index = 0
    while allocations and remaining > 0:
        allocations[allocation_index % len(allocations)]["limit"] += 1
        remaining -= 1
        allocation_index += 1
    return allocations


def _generation_method_for_origin(origin: str, active_modes: list[str]) -> str | None:
    clean = origin.strip()
    if not clean:
        return None
    if clean in active_modes:
        return clean
    if clean == "generation" and "paper_seeded_idea_generation" in active_modes:
        return "paper_seeded_idea_generation"
    if ":" in clean:
        suffix = clean.rsplit(":", 1)[-1]
        if suffix in active_modes:
            return suffix
    if "paper_seeded_idea_generation" in active_modes and clean in {
        "anthropic",
        "anthropic-haiku",
        "llm",
        "openai",
    }:
        return "paper_seeded_idea_generation"
    return None


def _generation_allocation_reason(
    mode: str,
    *,
    active_counts: Counter[str],
    merged_counts: Counter[str],
    cluster_ids_by_mode: dict[str, set[str]],
    control_counts: Counter[str],
) -> str:
    active = active_counts[mode]
    merged = merged_counts[mode]
    cluster_count = len(cluster_ids_by_mode[mode])
    controls = control_counts[mode]
    parts: list[str] = []
    if active == 0:
        parts.append("underrepresented: no active hypotheses")
    else:
        parts.append(f"{active} active hypothesis{'es' if active != 1 else ''}")
    if merged:
        parts.append(f"{merged} merged duplicate{'s' if merged != 1 else ''}")
    if cluster_count:
        parts.append(f"{cluster_count} proximity cluster saturation signal{'s' if cluster_count != 1 else ''}")
    if controls:
        parts.append(f"{controls} duplicate/diversity control signal{'s' if controls != 1 else ''}")
    if not parts:
        parts.append("balanced coverage")
    return "; ".join(parts)


def _allocation_limit(allocation: dict[str, Any]) -> int:
    value = allocation.get("limit", 0)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _plan_allows_external_tools(plan: ResearchPlanConfig) -> bool:
    normalized = {tool.strip().lower().replace("-", "_") for tool in plan.allowed_tools if tool.strip()}
    inert_tools = {"deterministic_agents", "deterministic_agent"}
    return bool(normalized - inert_tools)


def _plan_allows_benchmark_tools(plan: ResearchPlanConfig) -> bool:
    normalized = [tool.strip().lower().replace("-", "_") for tool in plan.allowed_tools if tool.strip()]
    markers = ("benchmark", "simulation", "simulator", "eval", "evaluation", "metric")
    return any(any(marker in tool for marker in markers) for tool in normalized)


def _plan_needs_deep_verification(plan: ResearchPlanConfig) -> bool:
    normalized = {
        value.strip().lower().replace("-", "_")
        for value in [*plan.allowed_tools, *plan.allowed_sources]
        if value.strip()
    }
    markers = (
        "literature",
        "publication",
        "full_text",
        "openalex",
        "benchmark",
        "simulation",
        "simulator",
        "eval",
        "evaluation",
        "metric",
        "validation",
        "verification",
    )
    return any(any(marker in value for marker in markers) for value in normalized)


def _plan_needs_safety_review(plan: ResearchPlanConfig) -> bool:
    normalized = {
        value.strip().lower().replace("-", "_")
        for value in [*plan.allowed_tools, *plan.allowed_sources]
        if value.strip()
    }
    inert_sources = {
        "deterministic_agents",
        "deterministic_agent",
        "seed_paper_evidence",
        "local_evidence_paths",
    }
    markers = (
        "web",
        "search",
        "repo",
        "repository",
        "tool",
        "openalex",
        "literature",
        "full_text",
        "private",
        "indexed",
        "crawl",
        "url",
    )
    return any(
        value not in inert_sources and any(marker in value for marker in markers)
        for value in normalized
    )


def _active_review_types(plan: ResearchPlanConfig, use_grounded: bool) -> list[str]:
    review_types = list(plan.review_types or ["initial_review"])
    evidence_aware = {
        "full_review",
        "novelty_review",
        "deep_verification",
        "observation_review",
        "simulation_review",
    }
    if use_grounded and not evidence_aware.intersection(review_types):
        review_types.append("full_review")
    if use_grounded and _plan_needs_safety_review(plan) and "safety_review" not in review_types:
        review_types.append("safety_review")
    if use_grounded and _plan_needs_deep_verification(plan) and "deep_verification" not in review_types:
        review_types.append("deep_verification")
    if use_grounded and _plan_allows_external_tools(plan) and "observation_review" not in review_types:
        review_types.append("observation_review")
    if use_grounded and _plan_allows_benchmark_tools(plan) and "simulation_review" not in review_types:
        review_types.append("simulation_review")
    return review_types


def _active_evolution_strategy(
    plan: ResearchPlanConfig,
    cycle: int,
    use_grounded: bool = False,
) -> str:
    strategies = list(plan.evolution_strategies or ["simplification"])
    if use_grounded and _plan_allows_external_tools(plan):
        strategies = [
            "evidence_grounding",
            *[strategy for strategy in strategies if strategy != "evidence_grounding"],
        ]
    if not strategies:
        return "simplification"
    index = max(cycle - 1, 0) % len(strategies)
    return strategies[index].strip().lower().replace("-", "_") or "simplification"


def _use_multi_round_debate(plan: ResearchPlanConfig) -> bool:
    signals = [
        *plan.generation_methods,
        *plan.review_types,
        *plan.allowed_tools,
    ]
    normalized = {signal.lower().replace("-", "_") for signal in signals}
    return bool({"simulated_debate", "multi_round_debate", "multi_turn_debate"} & normalized)


def _apply_safety_quarantine(hypotheses: list[Hypothesis], reviews: list[Review]) -> list[Hypothesis]:
    rejected_ids = _safety_rejected_hypothesis_ids(reviews)
    if not rejected_ids:
        return hypotheses
    return [
        item.with_status("quarantined")
        if item.id in rejected_ids and item.status not in _INACTIVE_STATUSES
        else item
        for item in hypotheses
    ]


def _quarantine_unsafe_loaded_hypotheses(
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    safety_policies: list[SafetyPolicy] | None = None,
) -> tuple[list[Hypothesis], list[Review]]:
    """Quarantine unsafe hypotheses at ingestion (state load / manual additions).

    Runs the deterministic hypothesis safety gate over every loaded hypothesis so
    pre-existing or manually injected candidates cannot enter the tournament,
    evolution, or research output when they violate safety boundaries. Emits a
    synthetic safety_review reject Review for audit when none exists yet.
    """
    already_rejected = _safety_rejected_hypothesis_ids(reviews)
    updated: list[Hypothesis] = []
    new_reviews: list[Review] = []
    for hypothesis in hypotheses:
        if hypothesis.status in _INACTIVE_STATUSES:
            updated.append(hypothesis)
            continue
        decision = review_hypothesis_safety(hypothesis, safety_policies=safety_policies or [])
        if decision.allowed:
            updated.append(hypothesis)
            continue
        updated.append(hypothesis.with_status("quarantined"))
        if hypothesis.id not in already_rejected:
            new_reviews.append(
                Review(
                    id=stable_id("rev", f"safety-ingestion:{hypothesis.id}"),
                    hypothesis_id=hypothesis.id,
                    decision="reject",
                    scores={"safety": 1},
                    strengths=[],
                    weaknesses=list(decision.flags),
                    safety_notes=[decision.reason],
                    review_type="safety_review",
                    findings=[
                        f"Hypothesis safety gate blocked this candidate at ingestion: {decision.reason}"
                    ],
                    confidence=0.9,
                    requires_revision=True,
                )
            )
    return updated, new_reviews


def _accepted_hypothesis_ids(hypotheses: list[Hypothesis], reviews: list[Review]) -> set[str]:
    reviews_by_hypothesis: dict[str, list[Review]] = {item.id: [] for item in hypotheses}
    for review in reviews:
        reviews_by_hypothesis.setdefault(review.hypothesis_id, []).append(review)
    return {
        hypothesis_id
        for hypothesis_id, hypothesis_reviews in reviews_by_hypothesis.items()
        if hypothesis_reviews and all(review.decision == "accept" for review in hypothesis_reviews)
    }


def _replace_hypotheses(existing: list[Hypothesis], replacements: list[Hypothesis]) -> list[Hypothesis]:
    by_id = {item.id: item for item in existing}
    for item in replacements:
        by_id[item.id] = item
    return list(by_id.values())


def _merge_hypotheses(existing: list[Hypothesis], additions: list[Hypothesis]) -> list[Hypothesis]:
    by_id = {item.id: item for item in existing}
    for item in additions:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def _apply_proximity_deduplication(
    hypotheses: list[Hypothesis],
    proximity_edges: list[ProximityEdge],
) -> list[Hypothesis]:
    if not hypotheses or not proximity_edges:
        return hypotheses
    by_id = {item.id: item for item in hypotheses}
    for edge in sorted(proximity_edges, key=lambda item: item.similarity, reverse=True):
        source = by_id.get(edge.source)
        target = by_id.get(edge.target)
        if source is None or target is None:
            continue
        if edge.deduplication_action == "merge_or_contrast_before_ranking" and edge.similarity >= 0.75:
            keeper, duplicate = _deduplication_representative(source, target)
            keeper = by_id[keeper.id]
            duplicate = by_id[duplicate.id]
            if keeper.status in _INACTIVE_STATUSES or duplicate.status in _INACTIVE_STATUSES:
                continue
            active_count = len([item for item in by_id.values() if item.status not in _INACTIVE_STATUSES])
            if active_count <= 2:
                continue
            detail = _proximity_edge_detail(edge)
            keeper = _synthesize_proximity_representative(keeper, duplicate, edge)
            by_id[keeper.id] = _with_proximity_note(
                keeper,
                f"Kept as representative for duplicate {duplicate.id} via {detail}.",
            )
            by_id[duplicate.id] = _with_proximity_note(
                replace(duplicate, status="merged_duplicate", merged_into=keeper.id),
                f"Deduplicated into {keeper.id} via {detail}.",
            )
            continue
        if edge.diversity_action == "preserve_as_diversity_candidate":
            detail = _proximity_edge_detail(edge)
            for hypothesis_id in (edge.source, edge.target):
                item = by_id.get(hypothesis_id)
                if item is not None and item.status not in _INACTIVE_STATUSES:
                    by_id[hypothesis_id] = _with_proximity_note(
                        item,
                        f"Preserved for diversity via {detail}.",
                    )
    return [by_id[item.id] for item in hypotheses]


def _deduplication_representative(left: Hypothesis, right: Hypothesis) -> tuple[Hypothesis, Hypothesis]:
    if left.elo > right.elo:
        return left, right
    if right.elo > left.elo:
        return right, left
    return left, right


def _synthesize_proximity_representative(
    keeper: Hypothesis,
    duplicate: Hypothesis,
    edge: ProximityEdge,
) -> Hypothesis:
    synthesis_note = (
        f"Proximity synthesis from {duplicate.id}: {duplicate.claim} "
        f"(similarity {edge.similarity:.3f}; method {edge.method})."
    )
    rationale = keeper.rationale
    if synthesis_note not in rationale:
        rationale = f"{keeper.rationale} {synthesis_note}"
    trace_line = f"Proximity synthesis: merged {duplicate.id} into {keeper.id} via {_proximity_edge_detail(edge)}."
    generation_trace = list(keeper.generation_trace)
    if trace_line not in generation_trace:
        generation_trace.append(trace_line)
    return replace(
        keeper,
        rationale=rationale,
        assumptions=_bounded_unique([*keeper.assumptions, *duplicate.assumptions], limit=8),
        evidence_refs=_bounded_unique([*keeper.evidence_refs, *duplicate.evidence_refs], limit=12),
        risks=_bounded_unique([*keeper.risks, *duplicate.risks], limit=8),
        generation_trace=generation_trace,
    )


def _proximity_edge_detail(edge: ProximityEdge) -> str:
    reason = f": {edge.reason}" if edge.reason else ""
    return f"{edge.method} edge {edge.source}<->{edge.target} similarity {edge.similarity:.3f}{reason}"


def _with_proximity_note(hypothesis: Hypothesis, note: str) -> Hypothesis:
    notes = list(hypothesis.proximity_notes)
    if note not in notes:
        notes.append(note)
    return replace(hypothesis, proximity_notes=notes)


def _bounded_unique(items: list[str], limit: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _select_diverse_evolution_leaders(
    hypotheses: list[Hypothesis],
    proximity_edges: list[ProximityEdge],
    limit: int = 2,
) -> list[Hypothesis]:
    if limit <= 0:
        return []
    active = [
        item
        for item in sorted(hypotheses, key=lambda hyp: hyp.elo, reverse=True)
        if item.status not in _INACTIVE_STATUSES
    ]
    edge_by_pair = {_pair_key(edge.source, edge.target): edge for edge in proximity_edges}
    selected: list[Hypothesis] = []
    for candidate in active:
        if len(selected) >= limit:
            break
        if not selected or not any(
            _is_redundant_evolution_pair(candidate, chosen, edge_by_pair)
            for chosen in selected
        ):
            selected.append(candidate)

    selected_ids = {item.id for item in selected}
    for candidate in active:
        if len(selected) >= limit:
            break
        if candidate.id not in selected_ids:
            selected.append(candidate)
            selected_ids.add(candidate.id)
    return selected


def _is_redundant_evolution_pair(
    candidate: Hypothesis,
    selected: Hypothesis,
    edge_by_pair: dict[str, ProximityEdge],
) -> bool:
    edge = edge_by_pair.get(_pair_key(candidate.id, selected.id))
    if edge is None:
        return False
    if edge.deduplication_action == "merge_or_contrast_before_ranking":
        return True
    if edge.diversity_action == "preserve_as_diversity_candidate":
        return False
    return edge.similarity >= 0.8


def _schedule_pairs(
    hypotheses: list[Hypothesis],
    proximity_edges: list[ProximityEdge],
    matches: list[Match],
    max_matches: int,
    reviews: list[Review] | None = None,
) -> list[tuple[Hypothesis, Hypothesis]]:
    active_hypotheses = _active_hypotheses(hypotheses)
    if max_matches <= 0 or len(active_hypotheses) < 2:
        return []

    compared = {_pair_key(match.hypothesis_a, match.hypothesis_b) for match in matches}
    match_counts = Counter(item for match in matches for item in (match.hypothesis_a, match.hypothesis_b))
    review_counts = Counter(review.hypothesis_id for review in reviews or [])
    ranks = {item.id: index for index, item in enumerate(sorted(active_hypotheses, key=lambda hyp: hyp.elo, reverse=True))}
    similarities = {_pair_key(edge.source, edge.target): edge.similarity for edge in proximity_edges}
    edge_by_pair = {_pair_key(edge.source, edge.target): edge for edge in proximity_edges}

    candidates: list[tuple[float, str, Hypothesis, Hypothesis]] = []
    for first, second in combinations(active_hypotheses, 2):
        key = _pair_key(first.id, second.id)
        if key in compared:
            continue
        top_rank_bonus = (1.0 / (ranks[first.id] + 1)) + (1.0 / (ranks[second.id] + 1))
        newness_bonus = (1.0 / (match_counts[first.id] + 1)) + (1.0 / (match_counts[second.id] + 1))
        under_reviewed_bonus = (1.0 / (review_counts[first.id] + 1)) + (1.0 / (review_counts[second.id] + 1))
        similarity = similarities.get(key, 0.0)
        edge = edge_by_pair.get(key)
        semantic_bonus = 0.5 if edge and edge.method == "semantic_evidence_overlap" else 0.0
        embedding_bonus = 0.6 if edge and edge.method == "embedding_proximity" else 0.0
        evidence_bonus = min(len(edge.evidence_refs) * 0.25, 0.75) if edge else 0.0
        conflict_bonus = 0.5 if edge and any(
            marker in edge.reason.lower()
            for marker in ("contradict", "revise", "revision", "prior art")
        ) else 0.0
        deduplication_bonus = 0.8 if edge and edge.deduplication_action else 0.0
        diversity_bonus = 0.2 if edge and edge.diversity_action == "preserve_as_diversity_candidate" else 0.0
        score = (
            (2.0 * similarity)
            + top_rank_bonus
            + newness_bonus
            + (0.5 * under_reviewed_bonus)
            + semantic_bonus
            + embedding_bonus
            + evidence_bonus
            + conflict_bonus
            + deduplication_bonus
            + diversity_bonus
        )
        candidates.append((score, key, first, second))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(first, second) for _score, _key, first, second in candidates[:max_matches]]


def _pair_key(first_id: str, second_id: str) -> str:
    left, right = sorted([first_id, second_id])
    return f"{left}:{right}"


def _review_refs_for_pair(reviews: list[Review], first_id: str, second_id: str) -> list[str]:
    pair_ids = {first_id, second_id}
    return [review.id for review in reviews if review.hypothesis_id in pair_ids]


def _reviews_for_pair(reviews: list[Review], first_id: str, second_id: str) -> list[Review]:
    pair_ids = {first_id, second_id}
    return [review for review in reviews if review.hypothesis_id in pair_ids]


def _evidence_refs_for_hypotheses(hypotheses: list[Hypothesis]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for hypothesis in hypotheses:
        for ref in hypothesis.evidence_refs:
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _evidence_refs_for_edges(edges: list[ProximityEdge]) -> list[str]:
    return _unique_refs([ref for edge in edges for ref in edge.evidence_refs])


def _proximity_method(edges: list[ProximityEdge]) -> str:
    if any(edge.method == "llm_goal_aware_proximity" for edge in edges):
        return "llm_goal_aware_proximity"
    if any(edge.method == "embedding_proximity" for edge in edges):
        return "embedding_proximity"
    if any(edge.method == "semantic_evidence_overlap" for edge in edges):
        return "semantic_evidence_overlap"
    return "proximity"


def _unique_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref and ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique


def _build_agent_trace(
    cycle: int,
    agent: str,
    action: str,
    input_refs: list[str],
    output_refs: list[str],
    status: str = "completed",
    notes: str = "",
    evidence_refs: list[str] | None = None,
    task_id: str = "",
    llm_interactions: list[dict[str, str]] | None = None,
    scratchpad: list[str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> AgentTrace:
    trace_identity = (
        f"{cycle}:{agent}:{action}:{task_id}:{','.join(input_refs)}:"
        f"{','.join(output_refs)}:{status}:{notes}"
    )
    trace_id = stable_id("trace", trace_identity)
    trace_evidence_refs = evidence_refs or []
    trace_tool_calls = tool_calls or []
    if trace_evidence_refs and not trace_tool_calls:
        trace_tool_calls = [
            _evidence_context_tool_call(
                trace_id=trace_id,
                agent=agent,
                action=action,
                task_id=task_id,
                evidence_refs=trace_evidence_refs,
            )
        ]
    return AgentTrace(
        id=trace_id,
        cycle=cycle,
        agent=agent,
        action=action,
        task_id=task_id,
        input_refs=input_refs,
        output_refs=output_refs,
        status=status,
        notes=notes,
        evidence_refs=trace_evidence_refs,
        llm_interactions=llm_interactions or [],
        scratchpad=scratchpad or [],
        transcript_ref=f"transcripts/{agent}/{task_id or trace_id}.jsonl",
        tool_calls=trace_tool_calls,
    )


def _llm_complete_tool_call(trace: AgentTrace, interaction: dict[str, str], turn_index: int) -> dict[str, Any]:
    return {
        "id": stable_id("tool", f"{trace.id}:{turn_index}:llm.complete:{interaction.get('max_tokens', '')}"),
        "type": "llm_completion",
        "tool_name": "llm.complete",
        "turn": interaction.get("turn", ""),
        "status": "ok",
        "arguments": {
            "max_tokens": interaction.get("max_tokens", ""),
        },
    }


def _tool_calls_from_retrievals(retrievals: list[RetrievalMemoryRecord]) -> list[dict[str, Any]]:
    return [
        {
            "id": stable_id("tool", f"{record.id}:evidence_store.retrieve"),
            "type": "evidence_retrieval",
            "tool_name": "evidence_store.retrieve",
            "query": record.query,
            "retrieval_method": record.retrieval_method,
            "evidence_refs": record.evidence_refs,
            "citations": record.citations,
            "reason": record.reason,
            "status": "ok" if record.evidence_refs else "empty",
        }
        for record in retrievals
    ]


def _evidence_context_tool_call(
    *,
    trace_id: str,
    agent: str,
    action: str,
    task_id: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": stable_id("tool", f"{trace_id}:evidence_store.context_refs:{','.join(evidence_refs)}"),
        "type": "evidence_context",
        "tool_name": "evidence_store.context_refs",
        "agent": agent,
        "action": action,
        "task_id": task_id,
        "evidence_refs": evidence_refs,
        "status": "ok",
    }


def _trace_scratchpad(
    notes: list[str],
    retrievals: list[RetrievalMemoryRecord],
) -> list[str]:
    scratchpad = [note for note in notes if note]
    if retrievals:
        refs = _unique_refs(ref for record in retrievals for ref in record.evidence_refs)
        scratchpad.append(
            f"retrievals={len(retrievals)}; evidence_refs={', '.join(refs[:6]) or 'none'}"
        )
        for record in retrievals[:3]:
            scratchpad.append(
                f"retrieval query: {_shorten_text(record.query, 120)} -> "
                f"{', '.join(record.evidence_refs[:4]) or 'no evidence'}"
            )
    return scratchpad


def _shorten_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(limit - 3, 0)].rstrip()}..."


def create_task(
    cycle: int,
    plan: ResearchPlanConfig,
    kind: str,
    payload: dict[str, Any],
    result_refs: list[str] | None = None,
    status: str = "queued",
) -> Task:
    priority = _task_priority(plan, kind)
    task_payload = {"cycle": cycle, **payload}
    refs = list(result_refs or [])
    identity_payload = _task_identity_payload(task_payload)
    task_identity = (
        f"{cycle}:{kind}:{priority}:"
        f"{json.dumps(identity_payload, sort_keys=True)}:{','.join(refs)}"
    )
    return Task(
        id=stable_id("task", task_identity),
        kind=kind,
        priority=priority,
        payload=task_payload,
        status=status,
        result_refs=refs,
        worker_state={
            "phase": status,
            "last_event": "scheduled",
            "attempt": 0,
            "cycle": cycle,
        },
    )


def _task_identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    non_identity_keys = {"agent_feedback", "generation_allocations"}
    return {key: value for key, value in payload.items() if key not in non_identity_keys}


def score_task_priority(
    task: Task,
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis] | None = None,
    reviews: list[Review] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
    user_feedback: list[UserFeedback] | None = None,
    current_cycle: int | None = None,
    context_snapshots: list[ContextSnapshot] | None = None,
) -> float:
    score = max(task.priority, _task_priority(plan, task.kind, context_snapshots))
    hypothesis_refs = _task_hypothesis_refs(task)
    hypotheses_by_id = {item.id: item for item in hypotheses or []}
    related_hypotheses = [
        hypotheses_by_id[item_id]
        for item_id in hypothesis_refs
        if item_id in hypotheses_by_id
    ]
    related_reviews = [
        review
        for review in reviews or []
        if review.hypothesis_id in hypothesis_refs
    ]

    if related_hypotheses:
        top_elo = max(item.elo for item in related_hypotheses)
        score += min(max((top_elo - 1200.0) / 400.0, 0.0) * 0.25, 0.35)
        if any(not item.evidence_refs for item in related_hypotheses):
            score += 0.35
        if not related_reviews:
            score += 0.2
        elif any(review.requires_revision or not review.evidence_refs for review in related_reviews):
            score += 0.2

    task_cycle = _int_payload_value(task.payload.get("cycle"))
    if current_cycle is not None and task_cycle is not None:
        score += min(max(current_cycle - task_cycle, 0) * 0.05, 0.3)

    score += _proximity_cluster_bonus(task, hypothesis_refs, proximity_edges or [])
    score += _user_feedback_priority_delta(task, hypothesis_refs, user_feedback or [])
    return round(max(score, 0.001), 3)


def rescore_task_queue(
    tasks: list[Task],
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis] | None = None,
    reviews: list[Review] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
    user_feedback: list[UserFeedback] | None = None,
    current_cycle: int | None = None,
    context_snapshots: list[ContextSnapshot] | None = None,
) -> list[Task]:
    return [
        replace(
            task,
            priority=score_task_priority(
                task,
                plan=plan,
                hypotheses=hypotheses,
                reviews=reviews,
                proximity_edges=proximity_edges,
                user_feedback=user_feedback,
                current_cycle=current_cycle,
                context_snapshots=context_snapshots,
            ),
        )
        if task.status == "queued"
        else task
        for task in tasks
    ]


def select_scheduler_task_pool(
    tasks: list[Task],
    *,
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis] | None = None,
    reviews: list[Review] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
    user_feedback: list[UserFeedback] | None = None,
    current_cycle: int | None = None,
    context_snapshots: list[ContextSnapshot] | None = None,
    max_pool_size: int = 1,
    candidate_task_ids: set[str] | None = None,
    candidate_kinds: set[str] | None = None,
) -> list[Task]:
    rescored = rescore_task_queue(
        tasks,
        plan=plan,
        hypotheses=hypotheses,
        reviews=reviews,
        proximity_edges=proximity_edges,
        user_feedback=user_feedback,
        current_cycle=current_cycle,
        context_snapshots=context_snapshots,
    )
    queued = [
        task
        for task in rescored
        if task.status == "queued"
        and (candidate_task_ids is None or task.id in candidate_task_ids)
        and (candidate_kinds is None or task.kind in candidate_kinds)
    ]
    if not queued:
        return []
    selected = sorted(queued, key=lambda task: (-task.priority, task.id))[: max(max_pool_size, 1)]
    return [
        replace(
            task,
            worker_state=_task_worker_state(
                task,
                scheduler_decision={
                    "rank": rank,
                    "score": task.priority,
                    "candidate_count": len(queued),
                    "pool_size": len(selected),
                    "cycle": current_cycle,
                    "signals": _scheduler_decision_signals(
                        task,
                        plan=plan,
                        hypotheses=hypotheses,
                        reviews=reviews,
                        proximity_edges=proximity_edges,
                        user_feedback=user_feedback,
                        current_cycle=current_cycle,
                    ),
                },
            ),
        )
        for rank, task in enumerate(selected, start=1)
    ]


def _scheduler_decision_signals(
    task: Task,
    *,
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis] | None = None,
    reviews: list[Review] | None = None,
    proximity_edges: list[ProximityEdge] | None = None,
    user_feedback: list[UserFeedback] | None = None,
    current_cycle: int | None = None,
) -> list[str]:
    signals = [f"weight:{_task_weight_key(task.kind)}"]
    hypothesis_refs = _task_hypothesis_refs(task)
    hypotheses_by_id = {item.id: item for item in hypotheses or []}
    related_hypotheses = [
        hypotheses_by_id[item_id]
        for item_id in hypothesis_refs
        if item_id in hypotheses_by_id
    ]
    related_reviews = [
        review
        for review in reviews or []
        if review.hypothesis_id in hypothesis_refs
    ]

    if related_hypotheses:
        if any(item.elo > 1200.0 for item in related_hypotheses):
            signals.append("high_elo")
        if any(not item.evidence_refs for item in related_hypotheses):
            signals.append("missing_evidence")
        if not related_reviews:
            signals.append("review_gap")
        elif any(review.requires_revision or not review.evidence_refs for review in related_reviews):
            signals.append("revision_needed")

    task_cycle = _int_payload_value(task.payload.get("cycle"))
    if current_cycle is not None and task_cycle is not None:
        stale_cycles = max(current_cycle - task_cycle, 0)
        if stale_cycles:
            signals.append(f"stale_work:{stale_cycles}")

    cluster_ids = sorted(
        {
            edge.cluster_id
            for edge in _task_proximity_cluster_edges(task, hypothesis_refs, proximity_edges or [])
            if edge.cluster_id
        }
    )
    signals.extend(f"proximity_cluster:{cluster_id}" for cluster_id in cluster_ids)
    signals.extend(
        f"user_feedback:{item.id}"
        for item in user_feedback or []
        if _feedback_applies_to_task(item, task, hypothesis_refs)
    )
    return signals


def start_task(task: Task) -> Task:
    attempt = task.attempts + 1
    return replace(
        task,
        status="running",
        attempts=attempt,
        error="",
        worker_state=_task_worker_state(
            task,
            phase="running",
            last_event="started",
            attempt=attempt,
        ),
    )


def complete_task(task: Task, result_refs: list[str] | None = None) -> Task:
    refs = list(result_refs or [])
    return replace(
        task,
        status="completed",
        result_refs=refs,
        error="",
        worker_state=_task_worker_state(
            task,
            phase="completed",
            last_event="completed",
            attempt=task.attempts,
            result_refs=refs,
        ),
    )


def fail_task(task: Task, error: str, max_attempts: int = 3) -> Task:
    status = "failed" if task.attempts >= max(max_attempts, 1) else "queued"
    return replace(
        task,
        status=status,
        error=error,
        worker_state=_task_worker_state(
            task,
            phase=status,
            last_event="failed" if status == "failed" else "retry_scheduled",
            attempt=task.attempts,
            last_error=error,
            retryable=status == "queued",
        ),
    )


def defer_task(task: Task, reason: str) -> Task:
    return replace(
        task,
        status="deferred",
        error=reason,
        worker_state=_task_worker_state(
            task,
            phase="deferred",
            last_event="deferred",
            attempt=task.attempts,
            defer_reason=reason,
        ),
    )


def _task_worker_state(task: Task, **updates: Any) -> dict[str, Any]:
    state = dict(task.worker_state)
    state.update(updates)
    return state


def prepare_task_queue_for_resume(tasks: list[Task]) -> list[Task]:
    prepared: list[Task] = []
    positions: dict[str, int] = {}
    for task in tasks:
        resumed = _resume_task(task)
        existing_index = positions.get(resumed.id)
        if existing_index is None:
            positions[resumed.id] = len(prepared)
            prepared.append(resumed)
            continue
        prepared[existing_index] = _prefer_resume_task(prepared[existing_index], resumed)
    return prepared


def _resume_task(task: Task) -> Task:
    if task.status == "running":
        return replace(task, status="queued", error="resumed from interrupted running task")
    if task.status == "deferred" and "requested by control file" in task.error:
        return replace(task, status="queued", error="resumed from deferred control task")
    return task


def _prefer_resume_task(current: Task, candidate: Task) -> Task:
    if current.status == "completed" and candidate.status != "completed":
        return candidate
    if candidate.status == "completed" and current.status != "completed":
        return current
    if candidate.attempts > current.attempts:
        return candidate
    return current


def pick_next_task(tasks: list[Task]) -> Task | None:
    queued = [task for task in tasks if task.status == "queued"]
    if not queued:
        return None
    return sorted(queued, key=lambda task: (-task.priority, task.id))[0]


def _pick_next_tasks(tasks: list[Task], limit: int) -> list[Task]:
    queued = [task for task in tasks if task.status == "queued"]
    if not queued:
        return []
    return sorted(queued, key=lambda task: (-task.priority, task.id))[: max(limit, 1)]


def run_task_worker(
    tasks: list[Task],
    execute: Callable[[Task], list[str] | None],
    persist: Callable[[list[Task]], None] | None = None,
    max_attempts: int = 3,
    raise_on_failed: bool = False,
    eligible_task_ids: set[str] | None = None,
    defer_when: Callable[[], str | None] | None = None,
    max_concurrency: int = 1,
) -> list[Task]:
    task_queue = list(tasks)
    if persist:
        persist(task_queue)

    while True:
        eligible_tasks = (
            task_queue
            if eligible_task_ids is None
            else [task for task in task_queue if task.id in eligible_task_ids]
        )
        selected_tasks = _pick_next_tasks(eligible_tasks, max_concurrency)
        if not selected_tasks:
            return task_queue
        if defer_when:
            defer_reason = defer_when()
            if defer_reason:
                task_queue = _defer_queued_tasks(task_queue, defer_reason, eligible_task_ids)
                if persist:
                    persist(task_queue)
                return task_queue

        running_tasks = [start_task(task) for task in selected_tasks]
        for running in running_tasks:
            task_queue = _replace_task(task_queue, running)
        if persist:
            persist(task_queue)

        if len(running_tasks) == 1:
            task_queue = _execute_running_task(
                task_queue=task_queue,
                running=running_tasks[0],
                execute=execute,
                max_attempts=max_attempts,
                raise_on_failed=raise_on_failed,
            )
            if persist:
                persist(task_queue)
            continue

        failed_errors: list[BaseException] = []
        with ThreadPoolExecutor(max_workers=len(running_tasks)) as executor:
            future_by_task = {executor.submit(execute, task): task for task in running_tasks}
            for future in as_completed(future_by_task):
                running = future_by_task[future]
                try:
                    result_refs = future.result() or []
                except Exception as exc:
                    updated = fail_task(running, str(exc), max_attempts=max_attempts)
                    if updated.status == "failed" and raise_on_failed:
                        failed_errors.append(exc)
                else:
                    updated = complete_task(running, result_refs)
                task_queue = _replace_task(task_queue, updated)
        if persist:
            persist(task_queue)
        if failed_errors:
            raise failed_errors[0]


def _execute_running_task(
    task_queue: list[Task],
    running: Task,
    execute: Callable[[Task], list[str] | None],
    max_attempts: int,
    raise_on_failed: bool,
) -> list[Task]:
    try:
        result_refs = execute(running) or []
    except Exception as exc:
        updated = fail_task(running, str(exc), max_attempts=max_attempts)
        task_queue = _replace_task(task_queue, updated)
        if updated.status == "failed" and raise_on_failed:
            raise
        return task_queue
    completed = complete_task(running, result_refs)
    return _replace_task(task_queue, completed)


def _replace_task(tasks: list[Task], updated: Task) -> list[Task]:
    return [updated if task.id == updated.id else task for task in tasks]


def _defer_queued_tasks(
    tasks: list[Task],
    reason: str,
    eligible_task_ids: set[str] | None = None,
) -> list[Task]:
    return [
        defer_task(task, reason)
        if task.status == "queued" and (eligible_task_ids is None or task.id in eligible_task_ids)
        else task
        for task in tasks
    ]


def _task_hypothesis_refs(task: Task) -> list[str]:
    ref_keys = {
        "hypothesis_id",
        "hypothesis_ids",
        "leader_id",
        "leader_ids",
        "parent_id",
        "parent_ids",
        "top_hypothesis_id",
        "top_hypothesis_ids",
        "source",
        "target",
        "source_id",
        "target_id",
    }
    refs: list[str] = []
    seen: set[str] = set()
    for key in sorted(ref_keys):
        value = task.payload.get(key)
        for ref in _coerce_ref_list(value):
            if ref.startswith("hyp-") and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def _coerce_ref_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _int_payload_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _proximity_cluster_bonus(task: Task, hypothesis_refs: list[str], edges: list[ProximityEdge]) -> float:
    cluster_edges = _task_proximity_cluster_edges(task, hypothesis_refs, edges)
    if not cluster_edges:
        return 0.0
    semantic_bonus = 0.1 if any(edge.method == "semantic_evidence_overlap" for edge in cluster_edges) else 0.0
    embedding_bonus = 0.12 if any(edge.method == "embedding_proximity" for edge in cluster_edges) else 0.0
    evidence_bonus = min(
        len({ref for edge in cluster_edges for ref in edge.evidence_refs}) * 0.05,
        0.15,
    )
    control_bonus = 0.08 if any(
        edge.deduplication_action or edge.diversity_action for edge in cluster_edges
    ) else 0.0
    similarity_bonus = min(max(edge.similarity for edge in cluster_edges) * 0.15, 0.15)
    return 0.15 + semantic_bonus + embedding_bonus + evidence_bonus + control_bonus + similarity_bonus


def _task_proximity_cluster_edges(
    task: Task,
    hypothesis_refs: list[str],
    edges: list[ProximityEdge],
) -> list[ProximityEdge]:
    if not hypothesis_refs and not task.payload.get("cluster_id"):
        return []
    referenced = set(hypothesis_refs)
    payload_cluster = str(task.payload.get("cluster_id", ""))
    return [
        edge
        for edge in edges
        if edge.cluster_id
        and (
            edge.source in referenced
            or edge.target in referenced
            or edge.cluster_id == payload_cluster
        )
    ]


def _user_feedback_priority_delta(
    task: Task,
    hypothesis_refs: list[str],
    feedback: list[UserFeedback],
) -> float:
    if not feedback:
        return 0.0
    target_ids = {task.id, task.kind, *hypothesis_refs}
    delta = 0.0
    for item in feedback:
        ranking_delta = _preference_ranking_delta(item, hypothesis_refs)
        if ranking_delta:
            delta += ranking_delta
            continue
        if item.target_id not in target_ids:
            continue
        text = f"{item.kind} {item.influence} {item.content}".lower()
        if any(marker in text for marker in ("deprioritize", "ignore", "low priority", "scheduler_penalty")):
            delta -= 0.4
            continue
        if any(
            marker in text
            for marker in (
                "scheduler_boost",
                "priority",
                "prioritize",
                "verification",
                "deeper",
                "follow up",
            )
        ):
            delta += 0.45
        elif "informational" not in text:
            delta += 0.1
    return max(min(delta, 0.8), -0.8)


def _preference_ranking_delta(item: UserFeedback, hypothesis_refs: list[str]) -> float:
    if item.kind != "preference_ranking":
        return 0.0
    text = f"{item.influence} {item.content}".lower()
    delta = 0.0
    for ref in hypothesis_refs:
        ref_text = ref.lower()
        positive = (
            f"prefer {ref_text}" in text
            or f"rank {ref_text}" in text
            or f"{ref_text} over" in text
        )
        negative = (
            f"over {ref_text}" in text
            or f"deprioritize {ref_text}" in text
            or f"reject {ref_text}" in text
        )
        if positive:
            delta += 0.45
        if negative:
            delta -= 0.25
    return delta


def _feedback_applies_to_task(item: UserFeedback, task: Task, hypothesis_refs: list[str]) -> bool:
    if _preference_ranking_delta(item, hypothesis_refs):
        return True
    return item.target_id in {task.id, task.kind, *hypothesis_refs}


def _task_weight_key(kind: str) -> str:
    return {
        "generate": "generation",
        "review": "reflection",
        "proximity": "proximity",
        "ranking": "ranking",
        "evolution": "evolution",
        "meta_review": "meta_review",
        "overview": "meta_review",
        "research_outputs": "meta_review",
    }.get(kind, kind)


def _effective_scheduler_weights(
    plan: ResearchPlanConfig, context_snapshots: list[ContextSnapshot] | None
) -> dict[str, float]:
    if context_snapshots:
        latest = context_snapshots[-1].scheduler_weights
        if latest:
            return dict(latest)
    return dict(plan.scheduler_weights)


def _task_priority(
    plan: ResearchPlanConfig,
    kind: str,
    context_snapshots: list[ContextSnapshot] | None = None,
) -> float:
    weight_key = _task_weight_key(kind)
    weights = _effective_scheduler_weights(plan, context_snapshots)
    return round(max(weights.get(weight_key, 1.0), 0.001), 3)


def _build_context_snapshot(
    cycle: int,
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    matches: list[Match],
    meta_review_count: int,
    proximity_edges: list[ProximityEdge],
    max_hypotheses: int,
) -> ContextSnapshot:
    leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:3]
    scheduler_weights = _adjust_scheduler_weights(plan, hypotheses, reviews, matches, max_hypotheses)
    return ContextSnapshot(
        id=stable_id("ctx", f"{plan.id}:{cycle}:{len(hypotheses)}:{len(reviews)}:{len(matches)}"),
        cycle=cycle,
        generated_total=len(hypotheses),
        accepted_total=len([item for item in hypotheses if item.status == "accepted"]),
        review_total=len(reviews),
        match_total=len(matches),
        meta_review_total=meta_review_count,
        top_hypothesis_ids=[item.id for item in leaders],
        origin_counts=dict(Counter(item.origin for item in hypotheses)),
        status_counts=dict(Counter(item.status for item in hypotheses)),
        proximity_edge_count=len(proximity_edges),
        scheduler_weights=scheduler_weights,
        next_actions=[
            *_next_actions(hypotheses, reviews, matches, max_hypotheses),
            *unevaluated_termination_markers(plan),
        ],
    )


def _adjust_scheduler_weights(
    plan: ResearchPlanConfig,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    matches: list[Match],
    max_hypotheses: int,
) -> dict[str, float]:
    weights = dict(plan.scheduler_weights)
    if len(hypotheses) < max_hypotheses:
        weights["generation"] = weights.get("generation", 1.0) + 0.5
        weights["evolution"] = weights.get("evolution", 1.0) + 0.25
    if len(hypotheses) >= 2 and len(matches) < len(list(combinations(hypotheses, 2))):
        weights["ranking"] = weights.get("ranking", 1.0) + 0.5
        weights["proximity"] = weights.get("proximity", 1.0) + 0.25
    if reviews:
        weights["meta_review"] = weights.get("meta_review", 1.0) + 0.25
    return {key: round(value, 3) for key, value in sorted(weights.items())}


def _next_actions(
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    matches: list[Match],
    max_hypotheses: int,
) -> list[str]:
    actions: list[str] = []
    if len(hypotheses) < max_hypotheses:
        actions.append("generate_or_evolve_more_candidates")
    if len(hypotheses) >= 2 and len(matches) < len(list(combinations(hypotheses, 2))):
        actions.append("run_proximity_guided_tournament_matches")
    if reviews:
        actions.append("reuse_meta_review_feedback_in_next_cycle")
    if not actions:
        actions.append("render_research_overview_for_human_review")
    return actions
