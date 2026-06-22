from __future__ import annotations

import json
from collections import Counter
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
from code_scientist.llm import DEFAULT_ANTHROPIC_MODEL, AnthropicHaikuClient
from code_scientist.models import (
    ContextSnapshot,
    Hypothesis,
    Match,
    ProximityEdge,
    ResearchGoal,
    ResearchPlanConfig,
    Review,
    RunState,
    stable_id,
)
from code_scientist.paper import seed_paper_evidence
from code_scientist.safety import review_goal_safety


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
) -> RunState:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    goal = ResearchGoal.from_objective(objective)
    plan = ResearchPlanConfig.from_goal(goal)
    safety = review_goal_safety(goal.objective)
    state = RunState(goal=goal, plan=plan, evidence=seed_paper_evidence(), safety=safety)
    if not safety.allowed:
        _write_state(out_path / "state.json", state)
        return state

    generation = _build_generation_agent(
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        env_file=env_file,
        llm_client=llm_client,
    )
    reflection = ReflectionAgent()
    proximity = ProximityAgent()
    ranking = RankingAgent()
    evolution = EvolutionAgent()
    meta_review = MetaReviewAgent()

    hypotheses: list[Hypothesis] = []
    reviews: list[Review] = []
    matches: list[Match] = []
    proximity_edges: list[ProximityEdge] = []
    metas = []
    context_snapshots: list[ContextSnapshot] = []
    feedback: list[str] = []

    for cycle in range(1, cycles + 1):
        remaining = max(max_hypotheses - len(hypotheses), 0)
        generation_limit = remaining - min(2, remaining) if remaining > 2 else remaining
        existing_ids = {item.id for item in hypotheses}
        generated = [
            item
            for item in generation.generate(goal, state.evidence, limit=generation_limit)
            if item.id not in existing_ids
        ]
        reviewed = [reflection.review(goal, item) for item in generated]
        accepted_ids = {review.hypothesis_id for review in reviewed if review.decision == "accept"}
        accepted = [item.with_status("accepted") for item in generated if item.id in accepted_ids]
        hypotheses = _merge_hypotheses(hypotheses, accepted)
        reviews.extend(reviewed)

        proximity_edges = proximity.compute(hypotheses)
        for first, second in _schedule_pairs(hypotheses, proximity_edges, matches, max_matches):
            ranked_pair, match = ranking.compare(goal, first, second)
            hypotheses = _replace_hypotheses(hypotheses, ranked_pair)
            matches.append(match)

        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:2]
        child_limit = min(2, max(max_hypotheses - len(hypotheses), 0))
        if leaders and child_limit:
            children = evolution.evolve(goal, leaders, feedback, limit=child_limit)
            child_reviews = [reflection.review(goal, item) for item in children]
            accepted_child_ids = {review.hypothesis_id for review in child_reviews if review.decision == "accept"}
            hypotheses = _merge_hypotheses(
                hypotheses,
                [item.with_status("accepted") for item in children if item.id in accepted_child_ids],
            )
            reviews.extend(child_reviews)
            proximity_edges = proximity.compute(hypotheses)

        meta = meta_review.summarize(goal, reviews, matches)
        metas.append(meta)
        feedback = meta.prompt_feedback

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
        state = RunState(
            goal=goal,
            plan=plan,
            evidence=state.evidence,
            hypotheses=sorted(hypotheses, key=lambda item: item.elo, reverse=True),
            reviews=reviews,
            matches=matches,
            proximity_edges=proximity_edges,
            meta_reviews=metas,
            context_snapshots=context_snapshots,
            safety=safety,
        )
        _write_state(out_path / "state.json", state)

    state = RunState(
        goal=goal,
        plan=plan,
        evidence=state.evidence,
        hypotheses=sorted(hypotheses, key=lambda item: item.elo, reverse=True),
        reviews=reviews,
        matches=matches,
        proximity_edges=proximity_edges,
        meta_reviews=metas,
        context_snapshots=context_snapshots,
        safety=safety,
    )
    _write_state(out_path / "state.json", state)
    return state


def load_state(path: str | Path) -> RunState:
    return RunState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_state(path: Path, state: RunState) -> None:
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


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
        client = llm_client or AnthropicHaikuClient.from_environment(
            model=model or DEFAULT_ANTHROPIC_MODEL,
            env_path=env_file,
        )
        return GenerationAgent(llm_client=client, llm_max_tokens=max_tokens, llm_origin="anthropic-haiku")
    raise ValueError(f"Unknown provider: {provider}")


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


def _schedule_pairs(
    hypotheses: list[Hypothesis],
    proximity_edges: list[ProximityEdge],
    matches: list[Match],
    max_matches: int,
) -> list[tuple[Hypothesis, Hypothesis]]:
    if max_matches <= 0 or len(hypotheses) < 2:
        return []

    compared = {_pair_key(match.hypothesis_a, match.hypothesis_b) for match in matches}
    match_counts = Counter(item for match in matches for item in (match.hypothesis_a, match.hypothesis_b))
    ranks = {item.id: index for index, item in enumerate(sorted(hypotheses, key=lambda hyp: hyp.elo, reverse=True))}
    similarities = {_pair_key(edge.source, edge.target): edge.similarity for edge in proximity_edges}

    candidates: list[tuple[float, str, Hypothesis, Hypothesis]] = []
    for first, second in combinations(hypotheses, 2):
        key = _pair_key(first.id, second.id)
        if key in compared:
            continue
        top_rank_bonus = (1.0 / (ranks[first.id] + 1)) + (1.0 / (ranks[second.id] + 1))
        newness_bonus = (1.0 / (match_counts[first.id] + 1)) + (1.0 / (match_counts[second.id] + 1))
        similarity = similarities.get(key, 0.0)
        score = (2.0 * similarity) + top_rank_bonus + newness_bonus
        candidates.append((score, key, first, second))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(first, second) for _score, _key, first, second in candidates[:max_matches]]


def _pair_key(first_id: str, second_id: str) -> str:
    left, right = sorted([first_id, second_id])
    return f"{left}:{right}"


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
        next_actions=_next_actions(hypotheses, reviews, matches, max_hypotheses),
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
