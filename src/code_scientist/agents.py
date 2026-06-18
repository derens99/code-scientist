from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from typing import Any

from code_scientist.elo import update_elo
from code_scientist.llm import LLMResponseError
from code_scientist.models import Hypothesis, Match, MetaReview, ResearchGoal, Review, TestPlan, stable_id
from code_scientist.safety import review_hypothesis_safety


class GenerationAgent:
    def __init__(
        self,
        llm_client: Any | None = None,
        llm_max_tokens: int = 1024,
        llm_origin: str = "anthropic-haiku",
    ) -> None:
        self.llm_client = llm_client
        self.llm_max_tokens = llm_max_tokens
        self.llm_origin = llm_origin

    def generate(self, goal: ResearchGoal, evidence: list[Any], limit: int = 6) -> list[Hypothesis]:
        if self.llm_client:
            return self._generate_with_llm(goal, evidence, limit)

        evidence_refs = [getattr(item, "id", "") for item in evidence][:3]
        blueprints = [
            (
                "Critic-before-edit assumption decomposition",
                "A critic-before-edit loop that decomposes assumptions before patching will reduce bad repo-level fixes.",
                "False premises about call paths, invariants, and test scope are common causes of bad edits.",
                ["The agent can state assumptions before editing.", "A critic can catch false premises cheaply."],
                ["critic false negatives", "extra latency"],
            ),
            (
                "Tournament-ranked prompt variants",
                "Pairwise tournament ranking of prompt variants will identify more reliable coding-agent workflows than single-prompt selection.",
                "The paper's Elo tournament can be adapted to compare prompt and workflow hypotheses.",
                ["Prompt variants can be evaluated on comparable tasks.", "Pairwise judging is less noisy than absolute scoring."],
                ["judge bias", "overfitting to benchmark tasks"],
            ),
            (
                "Failure-derived benchmark seeds",
                "Mining prior failed agent traces into benchmark seeds will improve measurement of future workflow changes.",
                "Regression-focused evals need examples that reflect real observed failure modes.",
                ["Failure traces are available.", "Failures can be minimized into reproducible tasks."],
                ["private data leakage", "narrow benchmark coverage"],
            ),
            (
                "Memory with explicit contradiction checks",
                "Agent memory that records contradictions and stale facts will reduce repeated reasoning errors.",
                "Long-horizon agent work fails when memory is accepted without freshness checks.",
                ["Memory entries can be classified by freshness.", "Contradictions can be surfaced before planning."],
                ["memory bloat", "false contradiction alerts"],
            ),
            (
                "Tool-use budget scheduler",
                "A scheduler that allocates tool calls by uncertainty and expected information gain will reduce cost without lowering pass rate.",
                "The paper allocates compute based on tournament state; coding agents can allocate shell and search effort similarly.",
                ["Uncertainty can be estimated from reviews.", "Tool calls have measurable cost and value."],
                ["under-exploration", "bad uncertainty estimates"],
            ),
            (
                "Meta-review prompt feedback",
                "Summarizing recurring review critiques into prompt feedback will improve later generations without model training.",
                "The paper's meta-review loop enables process improvement through externalized feedback.",
                ["Recurring critique patterns are stable enough to reuse.", "Prompt feedback changes later hypotheses."],
                ["feedback overfitting", "generic critiques"],
            ),
        ]
        hypotheses: list[Hypothesis] = []
        for title, claim, rationale, assumptions, risks in blueprints[:limit]:
            identity = f"{goal.id}:{title}:{claim}"
            hypotheses.append(
                Hypothesis(
                    id=stable_id("hyp", identity),
                    title=title,
                    claim=claim,
                    rationale=rationale,
                    assumptions=assumptions,
                    evidence_refs=evidence_refs,
                    test_plan=TestPlan(
                        experiment=f"Compare baseline coding-agent workflow against: {title}.",
                        metrics=goal.metrics,
                        success_condition="Candidate improves pass rate or regression count without unacceptable cost increase.",
                    ),
                    risks=risks,
                    origin="generation",
                )
            )
        return hypotheses

    def _generate_with_llm(self, goal: ResearchGoal, evidence: list[Any], limit: int) -> list[Hypothesis]:
        response_text = self.llm_client.complete(
            _generation_prompt(goal, evidence, limit),
            max_tokens=self.llm_max_tokens,
        )
        return _parse_llm_hypotheses(
            response_text=response_text,
            goal=goal,
            evidence=evidence,
            limit=limit,
            origin=self.llm_origin,
        )


class ReflectionAgent:
    def review(self, goal: ResearchGoal, hypothesis: Hypothesis) -> Review:
        safety = review_hypothesis_safety(hypothesis)
        has_test = bool(hypothesis.test_plan.experiment and hypothesis.test_plan.metrics)
        has_evidence = bool(hypothesis.evidence_refs)
        scores = {
            "alignment": 5 if "agent" in hypothesis.claim.lower() or "llm" in hypothesis.claim.lower() else 3,
            "plausibility": 4 if hypothesis.assumptions else 2,
            "novelty": 4,
            "testability": 5 if has_test else 1,
            "safety": 5 if safety.allowed else 1,
        }
        weaknesses: list[str] = []
        if not has_evidence:
            weaknesses.append("missing evidence references")
        if not has_test:
            weaknesses.append("missing concrete test plan")
        if not safety.allowed:
            weaknesses.extend(safety.flags)
        if not weaknesses:
            weaknesses.append("needs measured benchmark evidence before claiming improvement")
        decision = "accept" if safety.allowed and has_test else "reject"
        return Review(
            id=stable_id("rev", f"{goal.id}:{hypothesis.id}:{decision}"),
            hypothesis_id=hypothesis.id,
            decision=decision,
            scores=scores,
            strengths=["structured hypothesis", "explicit assumptions", "concrete evaluation path"],
            weaknesses=weaknesses,
            safety_notes=[safety.reason],
        )


class ProximityAgent:
    def compute(self, hypotheses: list[Hypothesis]) -> list[dict[str, object]]:
        edges: list[dict[str, object]] = []
        for left, right in combinations(hypotheses, 2):
            left_tokens = set(_tokens(left.title + " " + left.claim))
            right_tokens = set(_tokens(right.title + " " + right.claim))
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
            edges.append({"source": left.id, "target": right.id, "similarity": round(similarity, 3)})
        return edges


class RankingAgent:
    def compare(self, goal: ResearchGoal, first: Hypothesis, second: Hypothesis) -> tuple[list[Hypothesis], Match]:
        first_score = _rank_score(first)
        second_score = _rank_score(second)
        winner, loser = (first, second) if first_score >= second_score else (second, first)
        winner_elo, loser_elo = update_elo(winner.elo, loser.elo)
        updated = {
            winner.id: winner.with_elo(winner_elo),
            loser.id: loser.with_elo(loser_elo),
        }
        ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
        match = Match(
            id=stable_id("match", f"{goal.id}:{first.id}:{second.id}"),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner.id,
            rationale=f"Selected {winner.title} because it has stronger structured evidence, assumptions, and testability.",
            elo_before={first.id: first.elo, second.id: second.elo},
            elo_after={item.id: item.elo for item in ranked},
        )
        return ranked, match


class EvolutionAgent:
    def evolve(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback: list[str],
        limit: int = 2,
    ) -> list[Hypothesis]:
        children: list[Hypothesis] = []
        for parent in parents[:limit]:
            feedback_text = "; ".join(feedback) if feedback else "tighten evidence and reduce evaluation cost"
            title = f"Simplified {parent.title}"
            claim = f"{parent.claim} A simplified variant should reduce cost and make evaluation easier."
            child = Hypothesis(
                id=stable_id("hyp", f"{goal.id}:{parent.id}:simplified:{feedback_text}"),
                title=title,
                claim=claim,
                rationale=f"Derived from {parent.title}; meta-review feedback: {feedback_text}.",
                assumptions=[*parent.assumptions, "The simplified variant preserves the core mechanism."],
                evidence_refs=parent.evidence_refs,
                test_plan=TestPlan(
                    experiment=f"Compare baseline, parent idea, and simplified variant for: {parent.title}.",
                    metrics=parent.test_plan.metrics,
                    success_condition="Simplified variant keeps reliability gains while reducing cost or complexity.",
                ),
                risks=[*parent.risks, "simplification may remove the useful mechanism"],
                origin="evolution",
                parent_ids=[parent.id],
            )
            children.append(child)
        return children


class MetaReviewAgent:
    def summarize(self, goal: ResearchGoal, reviews: list[Review], matches: list[Match]) -> MetaReview:
        weakness_counts = Counter(weakness for review in reviews for weakness in review.weaknesses)
        safety_counts = Counter(note for review in reviews for note in review.safety_notes)
        common_weaknesses = [item for item, _count in weakness_counts.most_common(5)]
        if not common_weaknesses:
            common_weaknesses = ["needs measured benchmark evidence before claiming improvement"]
        prompt_feedback = [
            "Require every hypothesis to name an experiment and metric.",
            "Prefer ideas with explicit assumptions and audit boundaries.",
            "Label Elo as proxy auto-evaluation rather than ground truth.",
        ]
        return MetaReview(
            id=stable_id("meta", f"{goal.id}:{len(reviews)}:{len(matches)}"),
            common_weaknesses=common_weaknesses,
            safety_concerns=[item for item, _count in safety_counts.most_common(3)],
            missing_evidence=["benchmark deltas", "repo-specific failure examples"],
            promising_directions=["critic loops", "evaluation design", "memory freshness", "tool-use scheduling"],
            prompt_feedback=prompt_feedback,
        )


def _tokens(text: str) -> list[str]:
    return [token.strip(".,:;()[]{}").lower() for token in text.split() if len(token.strip(".,:;()[]{}")) > 2]


def _rank_score(hypothesis: Hypothesis) -> int:
    return (
        len(hypothesis.assumptions)
        + len(hypothesis.evidence_refs)
        + len(hypothesis.test_plan.metrics)
        - len([risk for risk in hypothesis.risks if "unsafe" in risk.lower()])
    )


def _generation_prompt(goal: ResearchGoal, evidence: list[Any], limit: int) -> str:
    evidence_lines = []
    for item in evidence[:5]:
        evidence_lines.append(
            f"- {getattr(item, 'id', 'evidence')}: {getattr(item, 'content', '')} "
            f"Notes: {getattr(item, 'notes', '')}"
        )
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "- No evidence available."
    return f"""You are a coding-agent research scientist.
Generate {limit} testable hypotheses for this objective:
{goal.objective}

Evidence:
{evidence_text}

Return only valid JSON with this shape:
{{
  "hypotheses": [
    {{
      "title": "short title",
      "claim": "testable claim about improving LLM coding agents",
      "rationale": "why this could work",
      "assumptions": ["explicit assumption"],
      "risks": ["risk or failure mode"]
    }}
  ]
}}

Prefer ideas that are measurable with these metrics: {", ".join(goal.metrics)}.
Do not claim an improvement as proven; describe an experimentable hypothesis."""


def _parse_llm_hypotheses(
    response_text: str,
    goal: ResearchGoal,
    evidence: list[Any],
    limit: int,
    origin: str,
) -> list[Hypothesis]:
    try:
        parsed = json.loads(_strip_json_fence(response_text))
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM response was not valid hypothesis JSON.") from exc

    raw_hypotheses = parsed.get("hypotheses") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_hypotheses, list):
        raise LLMResponseError("LLM hypothesis JSON must be a list or object with a hypotheses list.")

    evidence_refs = [getattr(item, "id", "") for item in evidence][:3]
    hypotheses: list[Hypothesis] = []
    for raw_item in raw_hypotheses[:limit]:
        if not isinstance(raw_item, dict):
            raise LLMResponseError("Each LLM hypothesis must be a JSON object.")
        title = _required_text(raw_item, "title")
        claim = _required_text(raw_item, "claim")
        rationale = _required_text(raw_item, "rationale")
        identity = f"{goal.id}:{origin}:{title}:{claim}"
        hypotheses.append(
            Hypothesis(
                id=stable_id("hyp", identity),
                title=title,
                claim=claim,
                rationale=rationale,
                assumptions=_text_list(raw_item.get("assumptions")),
                evidence_refs=evidence_refs,
                test_plan=TestPlan(
                    experiment=f"Compare baseline coding-agent workflow against: {title}.",
                    metrics=goal.metrics,
                    success_condition="Candidate improves pass rate or regression count without unacceptable cost increase.",
                ),
                risks=_text_list(raw_item.get("risks")),
                origin=origin,
            )
        )
    if not hypotheses:
        raise LLMResponseError("LLM response did not include any hypotheses.")
    return hypotheses


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _required_text(raw_item: dict[str, Any], key: str) -> str:
    value = raw_item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LLMResponseError(f"LLM hypothesis missing required text field: {key}.")
    return " ".join(value.split())


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [" ".join(value.split())] if value.strip() else []
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if str(item).strip()]
    return []
