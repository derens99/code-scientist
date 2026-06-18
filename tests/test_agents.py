from code_scientist.agents import (
    EvolutionAgent,
    GenerationAgent,
    MetaReviewAgent,
    ProximityAgent,
    RankingAgent,
    ReflectionAgent,
)
from code_scientist.models import ResearchGoal
from code_scientist.paper import seed_paper_evidence


def test_generation_creates_structured_hypotheses():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=3)

    assert len(hypotheses) == 3
    assert all(item.test_plan.experiment for item in hypotheses)
    assert all(item.assumptions for item in hypotheses)


def test_reflection_accepts_testable_safe_hypothesis():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypothesis = GenerationAgent().generate(goal, seed_paper_evidence(), limit=1)[0]
    review = ReflectionAgent().review(goal, hypothesis)

    assert review.decision == "accept"
    assert review.scores["testability"] >= 4


def test_ranking_updates_leaderboard_with_match():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=2)
    ranked, match = RankingAgent().compare(goal, hypotheses[0], hypotheses[1])

    assert match.winner in {hypotheses[0].id, hypotheses[1].id}
    assert len(ranked) == 2
    assert ranked[0].elo != ranked[1].elo


def test_proximity_finds_similarity_edges():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=3)
    edges = ProximityAgent().compute(hypotheses)

    assert edges
    assert all(0.0 <= item["similarity"] <= 1.0 for item in edges)


def test_evolution_creates_child_without_replacing_parent():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    parent = GenerationAgent().generate(goal, seed_paper_evidence(), limit=1)[0]
    child = EvolutionAgent().evolve(goal, [parent], feedback=["Make experiments cheaper."])[0]

    assert child.id != parent.id
    assert child.parent_ids == [parent.id]
    assert parent.title in child.rationale


def test_meta_review_aggregates_weaknesses():
    goal = ResearchGoal.from_objective("Improve LLM coding agents")
    hypotheses = GenerationAgent().generate(goal, seed_paper_evidence(), limit=2)
    reviews = [ReflectionAgent().review(goal, item) for item in hypotheses]
    meta = MetaReviewAgent().summarize(goal, reviews, [])

    assert meta.common_weaknesses
    assert meta.prompt_feedback
