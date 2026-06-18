from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from code_scientist.agents import (
    EvolutionAgent,
    GenerationAgent,
    MetaReviewAgent,
    ProximityAgent,
    RankingAgent,
    ReflectionAgent,
)
from code_scientist.models import Hypothesis, ResearchGoal, RunState
from code_scientist.paper import seed_paper_evidence
from code_scientist.safety import review_goal_safety


def run_research_cycle(
    objective: str,
    cycles: int,
    max_hypotheses: int,
    max_matches: int,
    out_dir: str | Path,
) -> RunState:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    goal = ResearchGoal.from_objective(objective)
    safety = review_goal_safety(goal.objective)
    state = RunState(goal=goal, evidence=seed_paper_evidence(), safety=safety)
    if not safety.allowed:
        _write_state(out_path / "state.json", state)
        return state

    generation = GenerationAgent()
    reflection = ReflectionAgent()
    proximity = ProximityAgent()
    ranking = RankingAgent()
    evolution = EvolutionAgent()
    meta_review = MetaReviewAgent()

    hypotheses: list[Hypothesis] = []
    reviews = []
    matches = []
    metas = []
    feedback: list[str] = []

    for _cycle in range(cycles):
        remaining = max(max_hypotheses - len(hypotheses), 0)
        generated = generation.generate(goal, state.evidence, limit=remaining)
        reviewed = [reflection.review(goal, item) for item in generated]
        accepted_ids = {review.hypothesis_id for review in reviewed if review.decision == "accept"}
        accepted = [item.with_status("accepted") for item in generated if item.id in accepted_ids]
        hypotheses.extend(accepted)
        reviews.extend(reviewed)

        proximity.compute(hypotheses)
        for first, second in list(combinations(hypotheses, 2))[:max_matches]:
            ranked_pair, match = ranking.compare(goal, first, second)
            hypotheses = _replace_hypotheses(hypotheses, ranked_pair)
            matches.append(match)

        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:2]
        child_limit = max(1, min(2, max_hypotheses - len(hypotheses)))
        children = evolution.evolve(goal, leaders, feedback, limit=child_limit)
        child_reviews = [reflection.review(goal, item) for item in children]
        accepted_child_ids = {review.hypothesis_id for review in child_reviews if review.decision == "accept"}
        hypotheses.extend([item.with_status("accepted") for item in children if item.id in accepted_child_ids])
        reviews.extend(child_reviews)

        meta = meta_review.summarize(goal, reviews, matches)
        metas.append(meta)
        feedback = meta.prompt_feedback

    state = RunState(
        goal=goal,
        evidence=state.evidence,
        hypotheses=sorted(hypotheses, key=lambda item: item.elo, reverse=True),
        reviews=reviews,
        matches=matches,
        meta_reviews=metas,
        safety=safety,
    )
    _write_state(out_path / "state.json", state)
    return state


def load_state(path: str | Path) -> RunState:
    return RunState.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_state(path: Path, state: RunState) -> None:
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _replace_hypotheses(existing: list[Hypothesis], replacements: list[Hypothesis]) -> list[Hypothesis]:
    by_id = {item.id: item for item in existing}
    for item in replacements:
        by_id[item.id] = item
    return list(by_id.values())
