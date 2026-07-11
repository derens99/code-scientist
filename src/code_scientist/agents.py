from __future__ import annotations

import json
import re
import threading
from collections import Counter
from dataclasses import replace
from itertools import combinations
from typing import Any, Callable

from code_scientist.evidence import EvidenceStore
from code_scientist.elo import update_elo
from code_scientist.llm import LLMResponseError
from code_scientist.models import (
    AssumptionCheck,
    Evidence,
    Hypothesis,
    Match,
    MetaReview,
    ProximityEdge,
    ResearchGoal,
    ResearchOverview,
    ResearchOutputArtifact,
    Review,
    TestPlan,
    stable_id,
)
from code_scientist.safety import SafetyPolicy, review_evidence_safety, review_hypothesis_safety
from code_scientist.tools import AgentRetrievalRequest


class _TraceableLLMClient:
    def __init__(self, client: Any, sink_factory: Callable[[], list[dict[str, str]]]) -> None:
        self._client = client
        self._sink_factory = sink_factory

    def complete(self, prompt: str, max_tokens: int) -> str:
        response = self._client.complete(prompt, max_tokens=max_tokens)
        self._sink_factory().append(
            {
                "turn": _llm_turn_label(prompt),
                "prompt": str(prompt),
                "response": str(response),
                "max_tokens": str(max_tokens),
            }
        )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _LLMTraceMixin:
    def _init_llm_trace(self, llm_client: Any | None) -> None:
        self._llm_interactions_local = threading.local()
        self.llm_client = (
            _TraceableLLMClient(llm_client, self._llm_interactions_buffer)
            if llm_client is not None
            else None
        )

    def _llm_interactions_buffer(self) -> list[dict[str, str]]:
        buffer = getattr(self._llm_interactions_local, "records", None)
        if buffer is None:
            buffer = []
            self._llm_interactions_local.records = buffer
        return buffer

    def consume_llm_interactions(self) -> list[dict[str, str]]:
        buffer = self._llm_interactions_buffer()
        interactions = list(buffer)
        buffer.clear()
        return interactions


def _feedback_block(agent_feedback: list[str] | None) -> str:
    """Render prior-cycle meta-review feedback as a prompt block.

    Feedback conditions the *next* prompt an agent sees instead of mutating
    already-finished artifacts after the fact.
    """
    if not agent_feedback:
        return ""
    lines = "\n".join(f"- {item}" for item in agent_feedback)
    return f"\n\nMeta-review feedback from prior cycles (address these):\n{lines}\n"


def _goal_guidance_block(goal: ResearchGoal) -> str:
    sections = [
        ("Preferences", goal.preferences),
        ("Constraints", goal.constraints),
        ("Metrics", goal.metrics),
        ("Safety notes", goal.safety_notes),
        ("Allowed sources", goal.allowed_sources),
        ("Allowed tools", goal.allowed_tools),
        ("Output formats", goal.output_formats),
        ("Termination criteria", goal.termination_criteria),
    ]
    rendered = [
        f"{label}: {'; '.join(str(item) for item in values if str(item).strip())}"
        for label, values in sections
        if any(str(item).strip() for item in values)
    ]
    return "\n".join(rendered)


def _matched_feedback_terms(text: str, agent_feedback: list[str] | None) -> list[str]:
    if not agent_feedback:
        return []
    lowered = text.lower()
    return [term for term in agent_feedback if len(term) > 4 and term.lower() in lowered]


class GenerationAgent(_LLMTraceMixin):
    def __init__(
        self,
        llm_client: Any | None = None,
        llm_max_tokens: int = 1024,
        llm_origin: str = "anthropic-haiku",
    ) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens
        self.llm_origin = llm_origin

    def plan_retrieval_queries(
        self,
        goal: ResearchGoal,
        available_tools: list[str],
        *,
        iteration: int = 0,
        observations: list[Evidence] | None = None,
        agent_feedback: list[str] | None = None,
    ) -> list[AgentRetrievalRequest]:
        return _plan_agent_retrieval(
            llm_client=self.llm_client,
            llm_max_tokens=self.llm_max_tokens,
            agent="generation",
            goal=goal,
            available_tools=available_tools,
            subject=goal.objective,
            iteration=iteration,
            observations=observations or [],
            agent_feedback=agent_feedback,
        )

    def generate(
        self,
        goal: ResearchGoal,
        evidence: list[Any],
        limit: int = 6,
        agent_feedback: list[str] | None = None,
    ) -> list[Hypothesis]:
        if self.llm_client:
            return self._generate_with_llm(goal, evidence, limit, agent_feedback)

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
        if agent_feedback:
            filtered_blueprints = [
                blueprint
                for blueprint in blueprints
                if not _matched_feedback_terms(blueprint[1], agent_feedback)
            ]
            if filtered_blueprints:
                blueprints = filtered_blueprints

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
                    generation_trace=_generation_trace(
                        goal,
                        title,
                        evidence_refs,
                        len(assumptions),
                        "generation",
                    ),
                )
            )
        return hypotheses

    def generate_grounded(
        self,
        goal: ResearchGoal,
        evidence_store: EvidenceStore,
        limit: int = 6,
    ) -> list[Hypothesis]:
        goal_bundle = evidence_store.retrieve(goal.objective, limit=max(limit, 3))
        hypotheses = self.generate(goal, goal_bundle.evidence, limit=limit)
        grounded: list[Hypothesis] = []
        for hypothesis in hypotheses:
            bundle = evidence_store.retrieve(
                " ".join([hypothesis.title, hypothesis.claim, hypothesis.rationale]),
                limit=3,
            )
            if not bundle.evidence:
                grounded.append(hypothesis)
                continue
            refs = bundle.evidence_refs
            citation_note = "; ".join(bundle.citations[:2])
            grounded.append(
                replace(
                    hypothesis,
                    evidence_refs=refs,
                    rationale=(
                        f"{hypothesis.rationale} Retrieved evidence: {citation_note}."
                    ),
                    generation_trace=[
                        *hypothesis.generation_trace,
                        (
                            "Grounded retrieval query: "
                            f"{' '.join([hypothesis.title, hypothesis.claim, hypothesis.rationale])}"
                        ),
                        f"Grounded retrieval evidence: {', '.join(refs) or 'none'}",
                    ],
                )
            )
        return grounded

    def generate_with_mode(
        self,
        goal: ResearchGoal,
        evidence: list[Any] | EvidenceStore,
        mode: str,
        limit: int = 6,
        agent_feedback: list[str] | None = None,
        existing_hypotheses: list[Hypothesis] | None = None,
        research_overview: Any | None = None,
    ) -> list[Hypothesis]:
        if mode == "paper_seeded_idea_generation":
            source_evidence = evidence.evidence if isinstance(evidence, EvidenceStore) else evidence
            return self.generate(goal, source_evidence, limit=limit, agent_feedback=agent_feedback)
        if mode == "literature_grounded_generation":
            store = evidence if isinstance(evidence, EvidenceStore) else EvidenceStore(evidence)
            return _grounded_mode_hypotheses(goal, store, limit)
        if mode == "tool_augmented_generation":
            store = evidence if isinstance(evidence, EvidenceStore) else EvidenceStore(evidence)
            if self.llm_client:
                return self._generate_tool_augmented_with_llm(goal, store, limit, agent_feedback)
            return _tool_augmented_hypotheses(goal, store, limit)
        if mode == "assumption_decomposition":
            source_evidence = evidence.evidence if isinstance(evidence, EvidenceStore) else evidence
            return _assumption_decomposition_hypotheses(goal, source_evidence, limit)
        if mode == "research_expansion_from_meta_review":
            source_evidence = evidence.evidence if isinstance(evidence, EvidenceStore) else evidence
            known = existing_hypotheses or []
            if self.llm_client:
                return self._generate_expansion_with_llm(
                    goal, source_evidence, limit, agent_feedback, known, research_overview
                )
            known_tokens = {
                token
                for item in known
                for token in _meaningful_terms(f"{item.title} {item.claim}")
            }
            overview_note = ""
            if research_overview is not None and getattr(research_overview, "limitations", None):
                overview_note = (
                    f" Overview gaps considered: {'; '.join(research_overview.limitations[:2])}."
                )
            candidates = self.generate(goal, source_evidence, limit=limit * 3, agent_feedback=agent_feedback)
            known_claims = {item.claim for item in known}
            fresh = [
                item
                for item in candidates
                if item.claim not in known_claims
                and len(known_tokens & _meaningful_terms(item.claim)) <= 2
            ] or [item for item in candidates if item.claim not in known_claims]
            return [
                replace(
                    item,
                    id=stable_id("hyp", f"{goal.id}:expansion:{item.id}"),
                    origin="generation:research_expansion_from_meta_review",
                    rationale=(
                        f"{item.rationale} Targets unexplored area relative to "
                        f"{len(known)} existing hypotheses.{overview_note}"
                    ),
                )
                for item in fresh[:limit]
            ]
        if mode in {"simulated_debate", "multi_round_debate", "multi_turn_debate"}:
            source_evidence = evidence.evidence if isinstance(evidence, EvidenceStore) else evidence
            if self.llm_client:
                return self._generate_debate_with_llm(goal, source_evidence, mode, limit, agent_feedback)
            return _simulated_debate_hypotheses(
                goal,
                self.generate(goal, source_evidence, limit=limit, agent_feedback=agent_feedback),
                mode,
            )
        return [
            replace(item, origin=f"generation:{mode}")
            for item in self.generate(
                goal,
                evidence.evidence if isinstance(evidence, EvidenceStore) else evidence,
                limit=limit,
                agent_feedback=agent_feedback,
            )
        ]

    def _generate_expansion_with_llm(
        self,
        goal: ResearchGoal,
        evidence: list[Any],
        limit: int,
        agent_feedback: list[str] | None,
        existing_hypotheses: list[Hypothesis],
        research_overview: Any | None,
    ) -> list[Hypothesis]:
        response_text = self.llm_client.complete(
            _generation_prompt(
                goal,
                evidence,
                limit,
                agent_feedback,
                expansion_context=_expansion_context_block(existing_hypotheses, research_overview),
            ),
            max_tokens=self.llm_max_tokens,
        )
        hypotheses = self._parse_llm_hypotheses_with_repair(
            response_text=response_text,
            goal=goal,
            evidence=evidence,
            limit=limit,
            origin=self.llm_origin,
        )
        known_claims = {item.claim for item in existing_hypotheses}
        deduped = [item for item in hypotheses if item.claim not in known_claims]
        return [
            replace(
                item,
                id=stable_id("hyp", f"{goal.id}:expansion:{item.id}"),
                origin="generation:research_expansion_from_meta_review",
                rationale=(
                    f"{item.rationale} Targets unexplored area relative to "
                    f"{len(existing_hypotheses)} existing hypotheses."
                ),
            )
            for item in deduped
        ]

    def _generate_with_llm(
        self,
        goal: ResearchGoal,
        evidence: list[Any],
        limit: int,
        agent_feedback: list[str] | None = None,
    ) -> list[Hypothesis]:
        response_text = self.llm_client.complete(
            _generation_prompt(goal, evidence, limit, agent_feedback),
            max_tokens=self.llm_max_tokens,
        )
        return self._parse_llm_hypotheses_with_repair(
            response_text=response_text,
            goal=goal,
            evidence=evidence,
            limit=limit,
            origin=self.llm_origin,
        )

    def _generate_debate_with_llm(
        self,
        goal: ResearchGoal,
        evidence: list[Any],
        mode: str,
        limit: int,
        agent_feedback: list[str] | None = None,
    ) -> list[Hypothesis]:
        proposal_text = self.llm_client.complete(
            _llm_debate_proposal_prompt(goal, evidence, mode, limit),
            max_tokens=self.llm_max_tokens,
        )
        critique_text = self.llm_client.complete(
            _llm_debate_critique_prompt(goal, evidence, mode, proposal_text),
            max_tokens=self.llm_max_tokens,
        )
        synthesis_text = self.llm_client.complete(
            _llm_debate_synthesis_prompt(
                goal, evidence, mode, proposal_text, critique_text, limit, agent_feedback
            ),
            max_tokens=self.llm_max_tokens,
        )
        hypotheses = self._parse_llm_hypotheses_with_repair(
            response_text=synthesis_text,
            goal=goal,
            evidence=evidence,
            limit=limit,
            origin=f"{self.llm_origin}:{mode}",
        )
        return _append_llm_generation_turn_trace(
            hypotheses,
            mode=mode,
            turns=[
                f"LLM turn 1 debate proposal: {_truncate(proposal_text, 220)}",
                f"LLM turn 2 debate critique: {_truncate(critique_text, 220)}",
                f"LLM turn 3 debate synthesis: {_truncate(synthesis_text, 220)}",
            ],
        )

    def _generate_tool_augmented_with_llm(
        self,
        goal: ResearchGoal,
        evidence_store: EvidenceStore,
        limit: int,
        agent_feedback: list[str] | None = None,
    ) -> list[Hypothesis]:
        selected = _select_tool_generation_evidence(goal, evidence_store, limit)
        if not selected:
            return []
        query_plan_text = self.llm_client.complete(
            _llm_tool_query_plan_prompt(goal, selected, limit),
            max_tokens=self.llm_max_tokens,
        )
        observation_text = self.llm_client.complete(
            _llm_tool_observation_prompt(goal, selected, query_plan_text),
            max_tokens=self.llm_max_tokens,
        )
        synthesis_text = self.llm_client.complete(
            _llm_tool_synthesis_prompt(goal, selected, query_plan_text, observation_text, limit, agent_feedback),
            max_tokens=self.llm_max_tokens,
        )
        hypotheses = self._parse_llm_hypotheses_with_repair(
            response_text=synthesis_text,
            goal=goal,
            evidence=selected,
            limit=limit,
            origin=f"{self.llm_origin}:tool_augmented_generation",
        )
        return _append_llm_generation_turn_trace(
            hypotheses,
            mode="tool_augmented_generation",
            turns=[
                f"LLM turn 1 tool query plan: {_truncate(query_plan_text, 220)}",
                f"LLM turn 2 tool observation analysis: {_truncate(observation_text, 220)}",
                f"LLM turn 3 tool synthesis: {_truncate(synthesis_text, 220)}",
            ],
        )

    def _parse_llm_hypotheses_with_repair(
        self,
        response_text: str,
        goal: ResearchGoal,
        evidence: list[Any],
        limit: int,
        origin: str,
    ) -> list[Hypothesis]:
        try:
            return _parse_llm_hypotheses(
                response_text=response_text,
                goal=goal,
                evidence=evidence,
                limit=limit,
                origin=origin,
            )
        except LLMResponseError:
            repair_text = self.llm_client.complete(
                _json_repair_prompt(goal, response_text, limit),
                max_tokens=max(self.llm_max_tokens, 1024),
            )
            return _parse_llm_hypotheses(
                response_text=repair_text,
                goal=goal,
                evidence=evidence,
                limit=limit,
                origin=origin,
            )


def _apply_deterministic_review_feedback(
    review: Review,
    hypothesis: Hypothesis,
    agent_feedback: list[str] | None,
) -> Review:
    """Ground deterministic reviews in the hypothesis text, not a blanket annotation."""
    hypothesis_text = " ".join([hypothesis.title, hypothesis.claim, hypothesis.rationale])
    matched_terms = _matched_feedback_terms(hypothesis_text, agent_feedback)
    if not matched_terms:
        return review
    findings = list(review.findings)
    for term in matched_terms:
        note = f"Prior meta-review flagged: {term}"
        if note not in findings:
            findings.append(note)
    return replace(review, findings=findings)


class ReflectionAgent(_LLMTraceMixin):
    def __init__(
        self,
        llm_client: Any | None = None,
        llm_max_tokens: int = 1024,
        safety_policies: list[SafetyPolicy] | None = None,
    ) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens
        self.safety_policies = safety_policies or []

    def plan_retrieval_queries(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        review_types: list[str],
        available_tools: list[str],
        *,
        iteration: int = 0,
        observations: list[Evidence] | None = None,
        agent_feedback: list[str] | None = None,
    ) -> list[AgentRetrievalRequest]:
        subject = "\n".join(
            [
                f"Hypothesis: {hypothesis.title}",
                f"Claim: {hypothesis.claim}",
                f"Assumptions: {'; '.join(hypothesis.assumptions)}",
                f"Review purposes: {', '.join(review_types)}",
            ]
        )
        return _plan_agent_retrieval(
            llm_client=self.llm_client,
            llm_max_tokens=self.llm_max_tokens,
            agent="reflection",
            goal=goal,
            available_tools=available_tools,
            subject=subject,
            iteration=iteration,
            observations=observations or [],
            agent_feedback=agent_feedback,
        )

    def review(self, goal: ResearchGoal, hypothesis: Hypothesis) -> Review:
        safety = review_hypothesis_safety(hypothesis, safety_policies=self.safety_policies)
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
            review_type="initial_review",
            evidence_refs=[ref for ref in hypothesis.evidence_refs if ref],
            findings=[],
            confidence=0.5,
            requires_revision=decision != "accept",
        )

    def full_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None = None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        if evidence_store is None:
            return _grounded_review_from_initial(
                initial,
                findings=["No evidence store configured; retained initial deterministic review decision."],
                evidence_refs=[],
                confidence=0.45,
                requires_revision=initial.decision != "accept",
                decision=initial.decision,
                weaknesses=initial.weaknesses,
            )

        evidence = evidence_store.search_hypothesis(hypothesis, limit=5)
        evidence_refs = [item.id for item in evidence]
        findings: list[str] = []
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        requires_revision = initial.requires_revision
        decision = initial.decision
        confidence = 0.65 if evidence else 0.45

        if not evidence:
            findings.append("No directly matching grounded evidence found; retained initial review decision.")
            if "missing grounded evidence" not in weaknesses:
                weaknesses.append("missing grounded evidence")

        for item in evidence:
            if _looks_contradictory(item.content):
                findings.append(
                    f"Evidence {item.id} from {item.source} contradicts the hypothesis: {item.content}"
                )
                if "contradicted by local evidence" not in weaknesses:
                    weaknesses.append("contradicted by local evidence")
                scores["plausibility"] = min(scores.get("plausibility", 3), 2)
                decision = "revise"
                requires_revision = True
                confidence = 0.8
            else:
                findings.append(f"Evidence {item.id} from {item.source} was considered: {item.content}")

        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=confidence,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
        )

    def review_with_type(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        review_type: str,
        evidence_store: EvidenceStore | None = None,
        agent_feedback: list[str] | None = None,
        matches: list[Match] | None = None,
        prior_reviews: list[Review] | None = None,
    ) -> Review:
        if self.llm_client:
            try:
                if review_type == "deep_verification":
                    return self._deep_verification_with_llm(goal, hypothesis, evidence_store, agent_feedback)
                if review_type == "safety_review":
                    return self._safety_review_with_llm(goal, hypothesis, evidence_store, agent_feedback)
                return self._review_with_llm(
                    goal, hypothesis, review_type, evidence_store, agent_feedback, matches
                )
            except LLMResponseError:
                pass
        if review_type == "initial_review":
            result = self.review(goal, hypothesis)
        elif review_type == "full_review":
            result = self.full_review(goal, hypothesis, evidence_store)
        elif review_type == "safety_review":
            result = self._safety_exploration_review(goal, hypothesis, evidence_store)
        elif review_type == "recurrent_tournament_review":
            base = self.review(goal, hypothesis)
            record = [m for m in (matches or []) if hypothesis.id in (m.hypothesis_a, m.hypothesis_b)]
            wins = sum(1 for m in record if m.winner == hypothesis.id)
            losses = sum(1 for m in record if m.winner not in ("", "tie", hypothesis.id))
            ties = sum(1 for m in record if m.winner == "tie")
            recurring = _recurring_weakness_terms(prior_reviews or [], hypothesis.id)
            findings = [
                *base.findings,
                f"Tournament record: won {wins}, lost {losses}, and tied {ties} of {len(record)} matches.",
            ]
            if recurring:
                findings.append(f"Recurring weaknesses across prior reviews: {', '.join(sorted(recurring)[:3])}.")
            result = replace(
                base,
                id=stable_id("rev", f"{goal.id}:{hypothesis.id}:{review_type}:{wins}:{losses}"),
                review_type=review_type,
                findings=findings,
            )
        elif review_type == "novelty_review":
            result = self._novelty_review(goal, hypothesis, evidence_store)
        elif review_type == "deep_verification":
            result = self._deep_verification_review(goal, hypothesis, evidence_store)
        elif review_type == "observation_review":
            result = self._observation_review(goal, hypothesis, evidence_store)
        elif review_type == "simulation_review":
            result = self._simulation_review(goal, hypothesis, evidence_store)
        else:
            base = self.review(goal, hypothesis)
            result = replace(
                base,
                id=stable_id("rev", f"{goal.id}:{hypothesis.id}:{review_type}:{base.decision}"),
                review_type=review_type,
            )
        return _apply_deterministic_review_feedback(result, hypothesis, agent_feedback)

    def _novelty_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        evidence = evidence_store.search_hypothesis(hypothesis, limit=5) if evidence_store else []
        evidence_refs = [item.id for item in evidence]
        findings: list[str] = []
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        requires_revision = initial.requires_revision
        decision = initial.decision
        for item in evidence:
            if _looks_like_prior_art(item.content):
                findings.append(f"Evidence {item.id} suggests prior art or known baseline: {item.content}")
                if "limited novelty relative to retrieved prior art" not in weaknesses:
                    weaknesses.append("limited novelty relative to retrieved prior art")
                scores["novelty"] = min(scores.get("novelty", 4), 2)
                requires_revision = True
                decision = "revise"
            else:
                findings.append(f"Evidence {item.id} was checked for novelty: {item.content}")
        if not findings:
            findings.append("No retrieved prior-art evidence found for this novelty review.")
        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=0.7 if evidence else 0.45,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
            review_type="novelty_review",
        )

    def _safety_exploration_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        turns = [
            (
                "autonomy and deployment",
                " ".join(
                    [
                        hypothesis.title,
                        hypothesis.claim,
                        "autonomous deployment production release human review local benchmark boundary",
                    ]
                ),
            ),
            (
                "data and credential exposure",
                " ".join(
                    [
                        hypothesis.title,
                        hypothesis.rationale,
                        "credentials secrets API keys private repository data leakage exfiltration",
                    ]
                ),
            ),
            (
                "source injection and benchmark gaming",
                " ".join(
                    [
                        hypothesis.title,
                        hypothesis.claim,
                        "prompt injection ignore previous instructions reveal secrets benchmark gaming unsafe repo mutation",
                    ]
                ),
            ),
        ]
        review_trace: list[str] = []
        evidence_by_id: dict[str, Any] = {}
        for index, (label, query) in enumerate(turns, start=1):
            turn_evidence = evidence_store.retrieve(query, limit=3).evidence if evidence_store else []
            for item in turn_evidence:
                evidence_by_id.setdefault(item.id, item)
            turn_refs = [item.id for item in turn_evidence]
            review_trace.append(f"Turn {index} query ({label}): {query}")
            review_trace.append(f"Turn {index} evidence: {', '.join(turn_refs) or 'none'}")
            for item in turn_evidence[:2]:
                review_trace.append(
                    f"Turn {index} observation: {item.id} {item.kind} from {item.source}: "
                    f"{_truncate(item.content, 180)}"
                )

        evidence = list(evidence_by_id.values())
        evidence_refs = _unique_refs([item.id for item in evidence])
        findings: list[str] = []
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        safety_notes = list(initial.safety_notes)
        safety = review_hypothesis_safety(hypothesis, safety_policies=self.safety_policies)
        flagged_evidence: dict[str, list[str]] = {}

        if not safety.allowed:
            findings.append(f"Hypothesis safety gate blocked this candidate: {safety.reason}")
            for flag in safety.flags:
                if flag not in weaknesses:
                    weaknesses.append(flag)
            safety_notes.append(f"Hypothesis safety flags: {', '.join(safety.flags)}.")

        if not evidence:
            findings.append("No retrieved safety-boundary evidence found for safety exploration.")

        for item in evidence:
            findings.append(f"Safety evidence {item.id} from {item.source}: {item.content}")
            decision = review_evidence_safety(item, safety_policies=self.safety_policies)
            if not decision.allowed:
                flagged_evidence[item.id] = decision.flags
                flag_text = ", ".join(decision.flags) or "flagged"
                findings.append(f"Evidence {item.id} failed safety screening: {decision.reason} ({flag_text}).")
                safety_notes.append(f"Evidence {item.id} flags: {flag_text}.")

        if flagged_evidence:
            if "retrieved safety evidence requires quarantine or revision" not in weaknesses:
                weaknesses.append("retrieved safety evidence requires quarantine or revision")
            scores["safety"] = min(scores.get("safety", 5), 2)

        requires_revision = initial.requires_revision or not safety.allowed or bool(flagged_evidence)
        if not safety.allowed:
            decision = "reject"
        elif flagged_evidence:
            decision = "revise"
        else:
            decision = initial.decision

        review_trace.append(
            "Safety assessment: "
            f"hypothesis_allowed={safety.allowed}; "
            f"flagged_evidence={len(flagged_evidence)}; "
            f"revision required: {requires_revision}."
        )
        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=0.8 if flagged_evidence or not safety.allowed else 0.65,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
            review_type="safety_review",
            review_trace=review_trace,
            safety_notes=safety_notes,
        )

    def _deep_verification_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        turns = [
            (
                "claim mechanism",
                " ".join([hypothesis.title, hypothesis.claim, "mechanism evidence prior work"]),
            ),
            (
                "assumptions and risks",
                " ".join([*hypothesis.assumptions, *hypothesis.risks, "assumption failure risk constraints"]),
            ),
            (
                "benchmark validation",
                " ".join([hypothesis.title, hypothesis.claim, "benchmark pass_rate regression_count deltas"]),
            ),
        ]
        review_trace: list[str] = []
        evidence_by_id: dict[str, Any] = {}
        evidence_by_turn: list[list[Any]] = []
        for index, (label, query) in enumerate(turns, start=1):
            turn_evidence = evidence_store.retrieve(query, limit=3).evidence if evidence_store else []
            evidence_by_turn.append(turn_evidence)
            for item in turn_evidence:
                evidence_by_id.setdefault(item.id, item)
            turn_refs = [item.id for item in turn_evidence]
            review_trace.append(f"Turn {index} query ({label}): {query}")
            review_trace.append(f"Turn {index} evidence: {', '.join(turn_refs) or 'none'}")
            for item in turn_evidence[:2]:
                review_trace.append(
                    f"Turn {index} observation: {item.id} {item.kind} from {item.source}: "
                    f"{_truncate(item.content, 180)}"
                )

        evidence = list(evidence_by_id.values())
        evidence_refs = _unique_refs([item.id for item in evidence])
        assumption_checks = _verify_explicit_assumptions(hypothesis, evidence_store)
        for index, check in enumerate(assumption_checks, start=1):
            review_trace.append(
                f"Assumption check {index} (depth {check.depth}; "
                f"{'fundamental' if check.fundamental else 'repairable'}): {check.assumption}"
            )
            review_trace.append(
                f"Assumption check {index} verdict: {check.verdict}; "
                f"evidence: {', '.join(check.evidence_refs) or 'none'}; {check.reasoning}"
            )
            for evidence_ref in check.evidence_refs:
                evidence_by_id.setdefault(
                    evidence_ref,
                    next(
                        (
                            item
                            for item in (evidence_store.evidence if evidence_store else [])
                            if item.id == evidence_ref
                        ),
                        None,
                    ),
                )
        evidence_by_id = {key: value for key, value in evidence_by_id.items() if value is not None}
        evidence = list(evidence_by_id.values())
        evidence_refs = _unique_refs([item.id for item in evidence])
        findings: list[str] = []
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        has_benchmark = any(item.kind == "benchmark_result" or "benchmark" in item.content.lower() for item in evidence)
        has_mechanism_evidence = bool(evidence_by_turn[0])
        has_assumption_evidence = bool(evidence_by_turn[1])
        for item in evidence:
            findings.append(f"Verification evidence {item.id} from {item.source}: {item.content}")
        for check in assumption_checks:
            findings.append(
                f"Assumption `{check.assumption}` was {check.verdict}; "
                f"fundamental={check.fundamental}; {check.reasoning}"
            )
        if not has_mechanism_evidence:
            findings.append("No mechanism evidence found for deep verification.")
            if "missing mechanism evidence for deep verification" not in weaknesses:
                weaknesses.append("missing mechanism evidence for deep verification")
        if not has_assumption_evidence:
            findings.append("No assumption or risk evidence found for deep verification.")
            if "missing assumption evidence for deep verification" not in weaknesses:
                weaknesses.append("missing assumption evidence for deep verification")
        if not has_benchmark:
            findings.append("No benchmark evidence found for deep verification.")
            if "missing benchmark evidence for deep verification" not in weaknesses:
                weaknesses.append("missing benchmark evidence for deep verification")
            scores["plausibility"] = min(scores.get("plausibility", 4), 3)
        fundamental_failures = [
            check
            for check in assumption_checks
            if check.verdict == "contradicted" and check.fundamental
        ]
        repairable_failures = [
            check
            for check in assumption_checks
            if check.verdict == "contradicted" and not check.fundamental
        ]
        if fundamental_failures:
            weaknesses.append("fundamental assumption contradicted during deep verification")
            scores["plausibility"] = 1
        elif repairable_failures:
            weaknesses.append("non-fundamental assumption requires repair")
            scores["plausibility"] = min(scores.get("plausibility", 4), 3)
        decision = initial.decision if has_benchmark else "revise"
        requires_revision = initial.requires_revision or not has_benchmark
        if fundamental_failures:
            decision = "reject"
            requires_revision = True
        elif repairable_failures:
            decision = "revise"
            requires_revision = True
        review_trace.append(
            "Assessment: "
            f"mechanism evidence {'found' if has_mechanism_evidence else 'missing'}; "
            f"assumption evidence {'found' if has_assumption_evidence else 'missing'}; "
            f"benchmark evidence {'found' if has_benchmark else 'missing'}; "
            f"assumptions checked={len(assumption_checks)}; "
            f"fundamental failures={len(fundamental_failures)}; "
            f"repairable failures={len(repairable_failures)}; "
            f"revision required: {requires_revision}."
        )
        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=0.75 if has_benchmark else 0.45,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
            review_type="deep_verification",
            review_trace=review_trace,
            assumption_checks=assumption_checks,
        )

    def _observation_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        query = " ".join([hypothesis.title, hypothesis.claim, "runtime observation failure trace repository logs"])
        evidence = _review_evidence_matching(evidence_store, query, _looks_like_observation_evidence)
        evidence_refs = [item.id for item in evidence]
        comparisons = [
            _compare_observation_to_hypothesis(hypothesis, item, index)
            for index, item in enumerate(evidence, start=1)
        ]
        findings = [
            f"Observation evidence {item.id} from {item.source}: {item.content}"
            for item in evidence
        ] + [comparison[1] for comparison in comparisons]
        review_trace = [f"Observation query: {query}"]
        for verdict, explanation, trace_lines in comparisons:
            review_trace.extend(trace_lines)
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        requires_revision = initial.requires_revision
        decision = initial.decision
        confidence = 0.7 if evidence else 0.45
        if not evidence:
            findings.append("No runtime, trace, repository, or tool observation evidence found.")
            if "missing observation evidence" not in weaknesses:
                weaknesses.append("missing observation evidence")
            requires_revision = True
            decision = "revise"
            scores["plausibility"] = min(scores.get("plausibility", 4), 3)
        elif any(verdict == "contradicts" for verdict, _, _ in comparisons):
            weaknesses.append("observed behavior contradicts the predicted mechanism")
            requires_revision = True
            decision = "revise"
            scores["plausibility"] = min(scores.get("plausibility", 4), 2)
        review_trace.append(
            "Observation assessment: "
            f"supports={sum(verdict == 'supports' for verdict, _, _ in comparisons)}; "
            f"contradicts={sum(verdict == 'contradicts' for verdict, _, _ in comparisons)}; "
            f"inconclusive={sum(verdict == 'inconclusive' for verdict, _, _ in comparisons)}."
        )
        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=confidence,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
            review_type="observation_review",
            review_trace=review_trace,
        )

    def _simulation_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
    ) -> Review:
        initial = self.review(goal, hypothesis)
        query = " ".join([hypothesis.title, hypothesis.claim, "simulation benchmark pass_rate regression_count"])
        evidence = _review_evidence_matching(evidence_store, query, _looks_like_simulation_evidence)
        evidence_refs = [item.id for item in evidence]
        comparisons = [
            _compare_observation_to_hypothesis(hypothesis, item, index, simulation=True)
            for index, item in enumerate(evidence, start=1)
        ]
        findings = [
            f"Simulation evidence {item.id} from {item.source}: {item.content}"
            for item in evidence
        ] + [comparison[1] for comparison in comparisons]
        review_trace = [
            f"Simulation step 1 - mechanism: {hypothesis.claim}",
            f"Simulation step 2 - intervention: {hypothesis.test_plan.experiment}",
            (
                "Simulation step 3 - expected measurements: "
                f"{', '.join(hypothesis.test_plan.metrics) or 'unspecified metrics'}; "
                f"success when {hypothesis.test_plan.success_condition}"
            ),
        ]
        for _verdict, _explanation, trace_lines in comparisons:
            review_trace.extend(trace_lines)
        review_trace.append(
            "Simulation step 4 - failure conditions: "
            f"{'; '.join(hypothesis.risks) or 'no explicit risks supplied'}"
        )
        weaknesses = list(initial.weaknesses)
        scores = dict(initial.scores)
        requires_revision = initial.requires_revision
        decision = initial.decision
        confidence = 0.75 if evidence else 0.45
        if not evidence:
            findings.append("No simulation, benchmark, prospective, or scaling evidence found.")
            if "missing simulation evidence" not in weaknesses:
                weaknesses.append("missing simulation evidence")
            requires_revision = True
            decision = "revise"
            scores["plausibility"] = min(scores.get("plausibility", 4), 3)
        elif any(verdict == "contradicts" for verdict, _, _ in comparisons):
            weaknesses.append("simulated outcome contradicts the expected success condition")
            requires_revision = True
            decision = "revise"
            scores["plausibility"] = min(scores.get("plausibility", 4), 2)
        review_trace.append(
            "Simulation step 5 - assessment: "
            f"supports={sum(verdict == 'supports' for verdict, _, _ in comparisons)}; "
            f"contradicts={sum(verdict == 'contradicts' for verdict, _, _ in comparisons)}; "
            f"inconclusive={sum(verdict == 'inconclusive' for verdict, _, _ in comparisons)}."
        )
        return _grounded_review_from_initial(
            initial,
            findings=findings,
            evidence_refs=evidence_refs,
            confidence=confidence,
            requires_revision=requires_revision,
            decision=decision,
            weaknesses=weaknesses,
            scores=scores,
            review_type="simulation_review",
            review_trace=review_trace,
        )

    def _review_with_llm(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        review_type: str,
        evidence_store: EvidenceStore | None,
        agent_feedback: list[str] | None = None,
        matches: list[Match] | None = None,
    ) -> Review:
        evidence = evidence_store.search_hypothesis(hypothesis, limit=5) if evidence_store else []
        response_text = self.llm_client.complete(
            _review_prompt(goal, hypothesis, review_type, evidence, agent_feedback, matches),
            max_tokens=self.llm_max_tokens,
        )
        return self._parse_llm_review(
            goal=goal,
            hypothesis=hypothesis,
            review_type=review_type,
            response_text=response_text,
            evidence=evidence,
            turn_trace=[],
        )

    def _deep_verification_with_llm(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
        agent_feedback: list[str] | None = None,
    ) -> Review:
        evidence = evidence_store.search_hypothesis(hypothesis, limit=5) if evidence_store else []
        mechanism_text = self.llm_client.complete(
            _llm_reflection_mechanism_prompt(goal, hypothesis, evidence),
            max_tokens=self.llm_max_tokens,
        )
        risk_text = self.llm_client.complete(
            _llm_reflection_risk_prompt(goal, hypothesis, evidence, mechanism_text),
            max_tokens=self.llm_max_tokens,
        )
        assumption_checks = _assumption_checks_from_llm_payload(
            risk_text,
            hypothesis=hypothesis,
            default_evidence_refs=[item.id for item in evidence],
        )
        synthesis_text = self.llm_client.complete(
            _llm_reflection_benchmark_synthesis_prompt(
                goal,
                hypothesis,
                evidence,
                mechanism_text,
                risk_text,
                agent_feedback,
            ),
            max_tokens=self.llm_max_tokens,
        )
        return self._parse_llm_review(
            goal=goal,
            hypothesis=hypothesis,
            review_type="deep_verification",
            response_text=synthesis_text,
            evidence=evidence,
            turn_trace=[
                f"LLM turn 1 claim mechanism: {_truncate(mechanism_text, 220)}",
                f"LLM turn 2 assumption risk audit: {_truncate(risk_text, 220)}",
                f"LLM turn 3 benchmark validation synthesis: {_truncate(synthesis_text, 220)}",
            ],
            assumption_checks=assumption_checks,
        )

    def _safety_review_with_llm(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        evidence_store: EvidenceStore | None,
        agent_feedback: list[str] | None = None,
    ) -> Review:
        evidence = evidence_store.search_hypothesis(hypothesis, limit=5) if evidence_store else []
        autonomy_text = self.llm_client.complete(
            _llm_reflection_autonomy_safety_prompt(goal, hypothesis, evidence),
            max_tokens=self.llm_max_tokens,
        )
        source_text = self.llm_client.complete(
            _llm_reflection_source_safety_prompt(goal, hypothesis, evidence, autonomy_text),
            max_tokens=self.llm_max_tokens,
        )
        synthesis_text = self.llm_client.complete(
            _llm_reflection_safety_synthesis_prompt(
                goal,
                hypothesis,
                evidence,
                autonomy_text,
                source_text,
                agent_feedback,
            ),
            max_tokens=self.llm_max_tokens,
        )
        return self._parse_llm_review(
            goal=goal,
            hypothesis=hypothesis,
            review_type="safety_review",
            response_text=synthesis_text,
            evidence=evidence,
            turn_trace=[
                f"LLM turn 1 autonomy and deployment red team: {_truncate(autonomy_text, 220)}",
                f"LLM turn 2 data and source-injection red team: {_truncate(source_text, 220)}",
                f"LLM turn 3 safety synthesis: {_truncate(synthesis_text, 220)}",
            ],
        )

    def _parse_llm_review(
        self,
        goal: ResearchGoal,
        hypothesis: Hypothesis,
        review_type: str,
        response_text: str,
        evidence: list[Any],
        turn_trace: list[str],
        assumption_checks: list[AssumptionCheck] | None = None,
    ) -> Review:
        data = _json_object(response_text, f"{review_type} review")
        decision = _clean_string(data.get("decision"), "revise")
        scores = _int_mapping(data.get("scores"))
        if not scores:
            scores = {"alignment": 3, "plausibility": 3, "novelty": 3, "testability": 3, "safety": 3}
        requires_revision = bool(data.get("requires_revision", decision != "accept"))
        parsed_assumption_checks = _assumption_checks_from_data(
            data.get("assumption_checks"),
            hypothesis=hypothesis,
            default_evidence_refs=[item.id for item in evidence],
        )
        assumption_checks = _merge_assumption_checks(
            list(assumption_checks or []),
            parsed_assumption_checks,
        )
        fundamental_failures = [
            check
            for check in assumption_checks
            if check.verdict == "contradicted" and check.fundamental
        ]
        repairable_failures = [
            check
            for check in assumption_checks
            if check.verdict == "contradicted" and not check.fundamental
        ]
        if fundamental_failures:
            decision = "reject"
            requires_revision = True
            scores["plausibility"] = 1
        elif repairable_failures:
            decision = "revise"
            requires_revision = True
            scores["plausibility"] = min(scores.get("plausibility", 3), 3)
        weaknesses = _string_list(
            data.get("weaknesses"),
            ["needs measured benchmark evidence before claiming improvement"],
        )
        findings = _string_list(data.get("findings"), [])
        if fundamental_failures:
            weaknesses = _unique_refs(
                [*weaknesses, "fundamental assumption contradicted during deep verification"]
            )
            findings = [
                *findings,
                *[
                    f"Fundamental assumption `{check.assumption}` was contradicted: {check.reasoning}"
                    for check in fundamental_failures
                ],
            ]
        elif repairable_failures:
            weaknesses = _unique_refs([*weaknesses, "non-fundamental assumption requires repair"])
            findings = [
                *findings,
                *[
                    f"Repairable assumption `{check.assumption}` was contradicted: {check.reasoning}"
                    for check in repairable_failures
                ],
            ]
        evidence_refs = _string_list(data.get("evidence_refs"), [item.id for item in evidence])
        review_trace = _string_list(data.get("review_trace"), [])
        if turn_trace:
            review_trace = [
                *review_trace,
                *turn_trace,
                (
                    "LLM multi-turn reflection assessment: "
                    f"type={review_type}; decision={decision}; "
                    f"evidence refs={len(evidence_refs)}; revision required: {requires_revision}."
                ),
            ]
        return Review(
            id=stable_id("rev", f"{goal.id}:{hypothesis.id}:llm:{review_type}:{decision}:{response_text}"),
            hypothesis_id=hypothesis.id,
            decision=decision,
            scores=scores,
            strengths=_string_list(data.get("strengths"), ["LLM reviewer produced a structured assessment."]),
            weaknesses=weaknesses,
            safety_notes=_string_list(data.get("safety_notes"), ["Human review required before code changes."]),
            review_type=f"llm_{review_type}",
            evidence_refs=evidence_refs,
            findings=findings,
            review_trace=review_trace,
            confidence=_bounded_float(data.get("confidence"), 0.5),
            requires_revision=requires_revision,
            assumption_checks=assumption_checks,
        )


class ProximityAgent(_LLMTraceMixin):
    def __init__(self, llm_client: Any | None = None, llm_max_tokens: int = 1024) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens

    def compute(self, hypotheses: list[Hypothesis]) -> list[ProximityEdge]:
        edges: list[ProximityEdge] = []
        for left, right in combinations(hypotheses, 2):
            left_tokens = set(_tokens(left.title + " " + left.claim))
            right_tokens = set(_tokens(right.title + " " + right.claim))
            union = left_tokens | right_tokens
            shared_tokens = sorted(left_tokens & right_tokens)
            similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
            reason = (
                f"Shared tokens: {', '.join(shared_tokens[:5])}"
                if shared_tokens
                else "No lexical overlap; retained as a low-similarity diversity edge."
            )
            cluster_basis = " ".join(shared_tokens[:3]) if shared_tokens else f"{left.id}:{right.id}:diverse"
            exploration_trace = [
                (
                    f"Turn 1 lexical/semantic overlap: shared tokens {', '.join(shared_tokens[:8])}"
                    if shared_tokens
                    else "Turn 1 lexical/semantic overlap: no shared tokens"
                ),
                "Turn 2 evidence overlap: lexical mode does not inspect evidence refs",
                "Turn 3 review context: lexical mode does not inspect reviews",
                f"Assessment: lexical similarity {round(similarity, 3):.3f}; cluster basis {cluster_basis}.",
            ]
            edges.append(
                ProximityEdge(
                    source=left.id,
                    target=right.id,
                    similarity=round(similarity, 3),
                    method="lexical_token_overlap",
                    reason=reason,
                    cluster_id=stable_id("cluster", cluster_basis),
                    exploration_trace=exploration_trace,
                )
            )
        return sorted(edges, key=lambda item: item.similarity, reverse=True)

    def compute_goal_aware(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        reviews: list[Review] | None = None,
        evidence_store: EvidenceStore | None = None,
        agent_feedback: list[str] | None = None,
    ) -> list[ProximityEdge]:
        if self.llm_client:
            try:
                return self._compute_goal_aware_with_llm(
                    goal, hypotheses, reviews or [], evidence_store, agent_feedback
                )
            except LLMResponseError:
                pass
        if evidence_store is not None and evidence_store.evidence:
            return self.compute_embedding(goal, hypotheses, reviews, evidence_store)
        return self.compute_semantic(hypotheses, reviews)

    def compute_semantic(
        self,
        hypotheses: list[Hypothesis],
        reviews: list[Review] | None = None,
    ) -> list[ProximityEdge]:
        reviews_by_hypothesis: dict[str, list[Review]] = {}
        for review in reviews or []:
            reviews_by_hypothesis.setdefault(review.hypothesis_id, []).append(review)

        edges: list[ProximityEdge] = []
        for left, right in combinations(hypotheses, 2):
            left_terms = _semantic_terms(left, reviews_by_hypothesis.get(left.id, []))
            right_terms = _semantic_terms(right, reviews_by_hypothesis.get(right.id, []))
            shared_terms = sorted(left_terms & right_terms)
            shared_evidence = sorted(set(left.evidence_refs) & set(right.evidence_refs))
            left_review_refs = [review.id for review in reviews_by_hypothesis.get(left.id, [])]
            right_review_refs = [review.id for review in reviews_by_hypothesis.get(right.id, [])]
            review_refs = [*left_review_refs, *right_review_refs]
            union = left_terms | right_terms
            term_similarity = len(shared_terms) / len(union) if union else 0.0
            evidence_bonus = min(len(shared_evidence) * 0.25, 0.5)
            similarity = min(1.0, term_similarity + evidence_bonus)
            reason_parts: list[str] = []
            if shared_evidence:
                reason_parts.append(f"Shared evidence: {', '.join(shared_evidence)}")
            if shared_terms:
                reason_parts.append(f"Shared semantic terms: {', '.join(shared_terms[:6])}")
            if review_refs:
                reason_parts.append(f"Review context: {', '.join(review_refs)}")
            if not reason_parts:
                reason_parts.append("No semantic overlap; retained as a diversity edge.")
            cluster_basis = " ".join(shared_evidence or shared_terms[:3] or [left.id, right.id])
            exploration_trace = [
                (
                    f"Turn 1 lexical/semantic overlap: shared terms {', '.join(shared_terms[:8])}"
                    if shared_terms
                    else "Turn 1 lexical/semantic overlap: no shared semantic terms"
                ),
                f"Turn 2 evidence overlap: {', '.join(shared_evidence) or 'none'}",
                f"Turn 3 review context: {', '.join(review_refs) or 'none'}",
                (
                    f"Assessment: semantic similarity {round(similarity, 3):.3f}; "
                    f"term component {term_similarity:.3f}; evidence bonus {evidence_bonus:.3f}."
                ),
            ]
            edges.append(
                ProximityEdge(
                    source=left.id,
                    target=right.id,
                    similarity=round(similarity, 3),
                    method="semantic_evidence_overlap",
                    reason="; ".join(reason_parts),
                    cluster_id=stable_id("cluster", cluster_basis),
                    evidence_refs=shared_evidence,
                    review_refs=review_refs,
                    exploration_trace=exploration_trace,
                )
            )
        return sorted(edges, key=lambda item: item.similarity, reverse=True)

    def compute_embedding(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        reviews: list[Review] | None,
        evidence_store: EvidenceStore,
    ) -> list[ProximityEdge]:
        reviews_by_hypothesis: dict[str, list[Review]] = {}
        for review in reviews or []:
            reviews_by_hypothesis.setdefault(review.hypothesis_id, []).append(review)

        retrieved_refs_by_hypothesis = {
            item.id: [
                evidence.id
                for evidence in evidence_store.search_embedding(
                    _proximity_embedding_query(item),
                    limit=1,
                )
            ]
            for item in hypotheses
        }

        edges: list[ProximityEdge] = []
        for left, right in combinations(hypotheses, 2):
            title_similarity = EvidenceStore.local_embedding_similarity(left.title, right.title)
            body_similarity = EvidenceStore.local_embedding_similarity(
                _proximity_embedding_query(left),
                _proximity_embedding_query(right),
            )
            embedding_similarity = max(title_similarity, body_similarity)
            shared_direct_evidence = sorted(set(left.evidence_refs) & set(right.evidence_refs))
            shared_retrieved_evidence = sorted(
                set(retrieved_refs_by_hypothesis.get(left.id, []))
                & set(retrieved_refs_by_hypothesis.get(right.id, []))
            )
            tool_evidence_refs = _tool_proximity_evidence_refs(goal, left, right, evidence_store)
            evidence_refs = _unique_refs([*shared_direct_evidence, *shared_retrieved_evidence, *tool_evidence_refs])
            left_review_refs = [review.id for review in reviews_by_hypothesis.get(left.id, [])]
            right_review_refs = [review.id for review in reviews_by_hypothesis.get(right.id, [])]
            review_refs = _unique_refs([*left_review_refs, *right_review_refs])
            evidence_bonus = min(len(evidence_refs) * 0.05, 0.1)
            similarity = min(1.0, embedding_similarity + evidence_bonus)
            deduplication_action, diversity_action = _proximity_control_actions(similarity, evidence_refs)
            method = "tool_backed_proximity" if tool_evidence_refs else "embedding_proximity"
            reason_parts = [
                (
                    f"Embedding similarity {similarity:.3f} "
                    f"(title {title_similarity:.3f}; body {body_similarity:.3f})"
                )
            ]
            if evidence_refs:
                reason_parts.append(f"Shared embedding evidence: {', '.join(evidence_refs)}")
            if tool_evidence_refs:
                reason_parts.append(f"Tool-backed proximity evidence: {', '.join(tool_evidence_refs)}")
            if review_refs:
                reason_parts.append(f"Review context: {', '.join(review_refs)}")
            if deduplication_action:
                reason_parts.append(f"Deduplication action: {deduplication_action}")
            if diversity_action:
                reason_parts.append(f"Diversity action: {diversity_action}")
            cluster_basis = " ".join(tool_evidence_refs or evidence_refs or [left.id, right.id, f"{similarity:.3f}"])
            exploration_trace = [
                (
                    "Turn 1 local embedding similarity: "
                    f"title {title_similarity:.3f}; body {body_similarity:.3f}; selected {similarity:.3f}"
                ),
                (
                    "Turn 2 embedding evidence overlap: "
                    f"direct={', '.join(shared_direct_evidence) or 'none'}; "
                    f"retrieved={', '.join(shared_retrieved_evidence) or 'none'}"
                ),
                f"Turn 3 review context: {', '.join(review_refs) or 'none'}",
                *(
                    [f"Turn 4 tool evidence exploration: {', '.join(tool_evidence_refs)}"]
                    if tool_evidence_refs
                    else []
                ),
                f"Deduplication control: {deduplication_action or 'none'}",
                f"Diversity control: {diversity_action or 'none'}",
                (
                    f"Assessment: {method} "
                    f"{round(similarity, 3):.3f}; evidence bonus {evidence_bonus:.3f}."
                ),
            ]
            edges.append(
                ProximityEdge(
                    source=left.id,
                    target=right.id,
                    similarity=round(similarity, 3),
                    method=method,
                    reason="; ".join(reason_parts),
                    cluster_id=stable_id("cluster", cluster_basis),
                    evidence_refs=evidence_refs,
                    review_refs=review_refs,
                    deduplication_action=deduplication_action,
                    diversity_action=diversity_action,
                    exploration_trace=exploration_trace,
                )
            )
        return sorted(edges, key=lambda item: item.similarity, reverse=True)

    def _compute_goal_aware_with_llm(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        reviews: list[Review],
        evidence_store: EvidenceStore | None,
        agent_feedback: list[str] | None = None,
    ) -> list[ProximityEdge]:
        neighborhood_text = self.llm_client.complete(
            _llm_proximity_neighborhood_prompt(goal, hypotheses, reviews, evidence_store),
            max_tokens=self.llm_max_tokens,
        )
        overlap_text = self.llm_client.complete(
            _llm_proximity_overlap_prompt(goal, hypotheses, reviews, evidence_store, neighborhood_text),
            max_tokens=self.llm_max_tokens,
        )
        synthesis_text = self.llm_client.complete(
            _llm_proximity_synthesis_prompt(
                goal,
                hypotheses,
                reviews,
                evidence_store,
                neighborhood_text,
                overlap_text,
                agent_feedback,
            ),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(synthesis_text, "goal-aware proximity")
        raw_edges = data.get("edges")
        if not isinstance(raw_edges, list):
            raise LLMResponseError("Goal-aware proximity response must contain an edges array.")

        hypothesis_ids = {item.id for item in hypotheses}
        known_review_ids = {review.id for review in reviews}
        parsed_edges: list[ProximityEdge] = []
        seen_pairs: set[tuple[str, str]] = set()
        llm_turn_trace = [
            f"LLM turn 1 semantic neighborhood mapping: {_truncate(neighborhood_text, 220)}",
            f"LLM turn 2 evidence and review overlap: {_truncate(overlap_text, 220)}",
            f"LLM turn 3 clustering synthesis: {_truncate(synthesis_text, 220)}",
        ]
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            source = _clean_string(raw_edge.get("source"), "")
            target = _clean_string(raw_edge.get("target"), "")
            if source not in hypothesis_ids or target not in hypothesis_ids or source == target:
                continue
            pair = tuple(sorted((source, target)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            evidence_refs = _unique_refs(_string_list(raw_edge.get("evidence_refs"), []))
            review_refs = [
                ref
                for ref in _unique_refs(_string_list(raw_edge.get("review_refs"), []))
                if ref in known_review_ids
            ]
            reason = _clean_string(
                raw_edge.get("reason"),
                "LLM proximity reviewer grouped these hypotheses for goal-aware follow-up.",
            )
            cluster_id = _clean_string(
                raw_edge.get("cluster_id"),
                stable_id("cluster", f"{goal.id}:{source}:{target}:{reason}"),
            )
            deduplication_action = _clean_string(raw_edge.get("deduplication_action"), "")
            diversity_action = _clean_string(raw_edge.get("diversity_action"), "")
            parsed_edges.append(
                ProximityEdge(
                    source=source,
                    target=target,
                    similarity=_bounded_float(raw_edge.get("similarity"), 0.5),
                    method="llm_goal_aware_proximity",
                    reason=reason,
                    cluster_id=cluster_id,
                    evidence_refs=evidence_refs,
                    review_refs=review_refs,
                    deduplication_action=deduplication_action,
                    diversity_action=diversity_action,
                    exploration_trace=[
                        *_string_list(raw_edge.get("exploration_trace"), []),
                        *llm_turn_trace,
                        (
                            "LLM multi-turn proximity assessment: "
                            f"edge={source}->{target}; similarity={_bounded_float(raw_edge.get('similarity'), 0.5):.3f}; "
                            f"evidence refs={len(evidence_refs)}; review refs={len(review_refs)}."
                        ),
                    ],
                )
            )
        if not parsed_edges:
            raise LLMResponseError("Goal-aware proximity response did not contain valid edges.")
        return sorted(parsed_edges, key=lambda item: item.similarity, reverse=True)


class RankingAgent(_LLMTraceMixin):
    def __init__(self, llm_client: Any | None = None, llm_max_tokens: int = 1024) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens

    def compare(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        review_refs: list[str] | None = None,
    ) -> tuple[list[Hypothesis], Match]:
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
            comparison_mode="heuristic_pairwise",
            judge_trace=(
                f"rank_score {first.id}={first_score} {second.id}={second_score}; "
                f"winner={winner.id}"
            ),
            uncertainty=round(1.0 / (1.0 + abs(first_score - second_score)), 3),
            review_refs=review_refs or [],
        )
        return ranked, match

    def compare_debate(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        reviews: list[Review] | None = None,
        evidence_store: EvidenceStore | None = None,
        agent_feedback: list[str] | None = None,
    ) -> tuple[list[Hypothesis], Match]:
        if self.llm_client:
            try:
                return self._compare_debate_with_llm(goal, first, second, reviews or [], agent_feedback)
            except LLMResponseError:
                pass
        first_reviews = [review for review in reviews or [] if review.hypothesis_id == first.id]
        second_reviews = [review for review in reviews or [] if review.hypothesis_id == second.id]
        first_score = _debate_score(first, first_reviews)
        second_score = _debate_score(second, second_reviews)
        first_manual_signal = _manual_review_signal(first_reviews)
        second_manual_signal = _manual_review_signal(second_reviews)
        score_delta = first_score - second_score
        retrieved_refs, retrieved_lines = _retrieve_pair_debate_evidence(evidence_store, first, second)
        evidence_refs = _unique_refs(
            [
                *first.evidence_refs,
                *second.evidence_refs,
                *(ref for review in first_reviews + second_reviews for ref in review.evidence_refs),
                *retrieved_refs,
            ]
        )
        review_refs = [review.id for review in first_reviews + second_reviews]
        transcript = [
            f"Pro {first.id}: evidence={len(first.evidence_refs)}, reviews={len(first_reviews)}, score={first_score:.2f}.",
            f"Pro {second.id}: evidence={len(second.evidence_refs)}, reviews={len(second_reviews)}, score={second_score:.2f}.",
            *retrieved_lines,
            f"Judge: score delta {score_delta:.2f}; uncertainty rises when hypotheses are close.",
        ]
        elo_before = {first.id: first.elo, second.id: second.elo}
        retrieved_trace = f"; retrieved_evidence={len(retrieved_refs)}" if evidence_store else ""

        if abs(score_delta) <= 0.5:
            ranked = sorted([first, second], key=lambda item: item.id)
            winner = "tie"
            outcome = "tie"
            elo_after = dict(elo_before)
            judge_trace = (
                f"debate_score {first.id}={first_score:.2f} {second.id}={second_score:.2f}; "
                f"manual_review {first.id}={first_manual_signal:.2f} {second.id}={second_manual_signal:.2f}; "
                f"abstain because scores are too close{retrieved_trace}"
            )
            rationale = "Debate judge abstained because evidence and review support were too close to separate."
            uncertainty = 1.0
        else:
            winner_hyp, loser_hyp = (first, second) if score_delta > 0 else (second, first)
            winner_elo, loser_elo = update_elo(winner_hyp.elo, loser_hyp.elo)
            updated = {
                winner_hyp.id: winner_hyp.with_elo(winner_elo),
                loser_hyp.id: loser_hyp.with_elo(loser_elo),
            }
            ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
            winner = winner_hyp.id
            outcome = "win"
            elo_after = {item.id: item.elo for item in ranked}
            judge_trace = (
                f"debate_score {first.id}={first_score:.2f} {second.id}={second_score:.2f}; "
                f"manual_review {first.id}={first_manual_signal:.2f} {second.id}={second_manual_signal:.2f}; "
                f"winner={winner}{retrieved_trace}"
            )
            rationale = (
                f"Debate judge selected {winner_hyp.title} using review support, evidence refs, "
                "testability, and revision penalties."
            )
            uncertainty = round(1.0 / (1.0 + abs(score_delta)), 3)

        match = Match(
            id=stable_id("match", f"{goal.id}:debate:{first.id}:{second.id}:{winner}"),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner,
            rationale=rationale,
            elo_before=elo_before,
            elo_after=elo_after,
            comparison_mode="deterministic_debate_judge",
            judge_trace=judge_trace,
            uncertainty=uncertainty,
            review_refs=review_refs,
            evidence_refs=evidence_refs,
            debate_transcript=transcript,
            outcome=outcome,
        )
        return ranked, match

    def compare_position_stable(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        reviews: list[Review] | None = None,
        evidence_store: EvidenceStore | None = None,
        agent_feedback: list[str] | None = None,
        *,
        multi_round: bool = False,
        rounds: int = 2,
    ) -> tuple[list[Hypothesis], Match]:
        """Judge A/B and B/A; abstain when presentation order changes the winner."""
        compare = self.compare_multi_round_debate if multi_round else self.compare_debate
        kwargs: dict[str, Any] = {
            "reviews": reviews,
            "evidence_store": evidence_store,
            "agent_feedback": agent_feedback,
        }
        if multi_round:
            kwargs["rounds"] = rounds
        forward_ranked, forward = compare(goal, first, second, **kwargs)
        _reverse_ranked, reverse = compare(goal, second, first, **kwargs)
        stable = forward.winner == reverse.winner
        stability_trace = (
            f"order_swap forward={forward.winner} reverse={reverse.winner}; "
            f"position_stable={str(stable).lower()}"
        )
        transcript = [
            *forward.debate_transcript,
            "Order-swapped replay:",
            *reverse.debate_transcript,
            f"Stability judge: {stability_trace}.",
        ]
        evidence_refs = _unique_refs([*forward.evidence_refs, *reverse.evidence_refs])
        review_refs = _unique_refs([*forward.review_refs, *reverse.review_refs])
        if stable:
            return forward_ranked, replace(
                forward,
                id=stable_id("match", f"{forward.id}:position_stable"),
                judge_trace=f"{forward.judge_trace}; {stability_trace}",
                debate_transcript=transcript,
                evidence_refs=evidence_refs,
                review_refs=review_refs,
            )

        ranked = sorted([first, second], key=lambda item: (-item.elo, item.id))
        return ranked, replace(
            forward,
            id=stable_id("match", f"{goal.id}:{first.id}:{second.id}:position_disagreement"),
            winner="tie",
            rationale=(
                "Order-swapped judges disagreed, so the ranking agent abstained and preserved "
                "both Elo ratings."
            ),
            elo_after={first.id: first.elo, second.id: second.elo},
            judge_trace=f"{forward.judge_trace}; {stability_trace}; abstain=position_disagreement",
            uncertainty=1.0,
            evidence_refs=evidence_refs,
            review_refs=review_refs,
            debate_transcript=transcript,
            outcome="tie",
        )

    def compare_multi_round_debate(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        reviews: list[Review] | None = None,
        rounds: int = 2,
        evidence_store: EvidenceStore | None = None,
        agent_feedback: list[str] | None = None,
    ) -> tuple[list[Hypothesis], Match]:
        round_count = max(2, rounds)
        if self.llm_client:
            try:
                return self._compare_multi_round_debate_with_llm(
                    goal,
                    first,
                    second,
                    reviews or [],
                    round_count,
                    agent_feedback,
                )
            except LLMResponseError:
                pass

        first_reviews = [review for review in reviews or [] if review.hypothesis_id == first.id]
        second_reviews = [review for review in reviews or [] if review.hypothesis_id == second.id]
        first_score = _debate_score(first, first_reviews)
        second_score = _debate_score(second, second_reviews)
        first_manual_signal = _manual_review_signal(first_reviews)
        second_manual_signal = _manual_review_signal(second_reviews)
        score_delta = first_score - second_score
        retrieved_refs, retrieved_lines = _retrieve_pair_debate_evidence(evidence_store, first, second)
        evidence_refs = _unique_refs(
            [
                *first.evidence_refs,
                *second.evidence_refs,
                *(ref for review in first_reviews + second_reviews for ref in review.evidence_refs),
                *retrieved_refs,
            ]
        )
        review_refs = [review.id for review in first_reviews + second_reviews]
        transcript = [
            f"Round 1 Pro {first.id}: evidence={len(first.evidence_refs)}, reviews={len(first_reviews)}, score={first_score:.2f}.",
            f"Round 1 Pro {second.id}: evidence={len(second.evidence_refs)}, reviews={len(second_reviews)}, score={second_score:.2f}.",
            *retrieved_lines,
        ]
        for round_index in range(2, round_count + 1):
            first_weaknesses = sum(len(review.weaknesses) for review in first_reviews)
            second_weaknesses = sum(len(review.weaknesses) for review in second_reviews)
            transcript.extend(
                [
                    (
                        f"Round {round_index} Rebuttal {first.id}: addresses {second.id} by contrasting "
                        f"{len(first.evidence_refs)} evidence refs against {second_weaknesses} opponent weaknesses."
                    ),
                    (
                        f"Round {round_index} Rebuttal {second.id}: addresses {first.id} by contrasting "
                        f"{len(second.evidence_refs)} evidence refs against {first_weaknesses} opponent weaknesses."
                    ),
                ]
            )
        elo_before = {first.id: first.elo, second.id: second.elo}

        if abs(score_delta) <= 0.5:
            ranked = sorted([first, second], key=lambda item: item.id)
            winner = "tie"
            outcome = "tie"
            elo_after = dict(elo_before)
            rationale = "Multi-round debate judge abstained because evidence and review support stayed too close to separate."
            uncertainty = 1.0
            transcript.append(f"Judge: abstained after {round_count} rounds because score delta was {score_delta:.2f}.")
            judge_trace = (
                f"multi_round_debate rounds={round_count}; "
                f"debate_score {first.id}={first_score:.2f} {second.id}={second_score:.2f}; "
                f"manual_review {first.id}={first_manual_signal:.2f} {second.id}={second_manual_signal:.2f}; "
                f"abstain because scores are too close; retrieved_evidence={len(retrieved_refs)}"
            )
        else:
            winner_hyp, loser_hyp = (first, second) if score_delta > 0 else (second, first)
            winner_elo, loser_elo = update_elo(winner_hyp.elo, loser_hyp.elo)
            updated = {
                winner_hyp.id: winner_hyp.with_elo(winner_elo),
                loser_hyp.id: loser_hyp.with_elo(loser_elo),
            }
            ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
            winner = winner_hyp.id
            outcome = "win"
            elo_after = {item.id: item.elo for item in ranked}
            rationale = (
                f"Multi-round debate judge selected {winner_hyp.title} after pro and rebuttal rounds "
                "using review support, evidence refs, testability, and revision penalties."
            )
            uncertainty = round(1.0 / (1.0 + abs(score_delta)), 3)
            transcript.append(f"Judge: selected {winner} after {round_count} rounds with score delta {score_delta:.2f}.")
            judge_trace = (
                f"multi_round_debate rounds={round_count}; "
                f"debate_score {first.id}={first_score:.2f} {second.id}={second_score:.2f}; "
                f"manual_review {first.id}={first_manual_signal:.2f} {second.id}={second_manual_signal:.2f}; "
                f"winner={winner}; retrieved_evidence={len(retrieved_refs)}"
            )

        match = Match(
            id=stable_id("match", f"{goal.id}:multi-round-debate:{round_count}:{first.id}:{second.id}:{winner}"),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner,
            rationale=rationale,
            elo_before=elo_before,
            elo_after=elo_after,
            comparison_mode="deterministic_multi_round_debate_judge",
            judge_trace=judge_trace,
            uncertainty=uncertainty,
            review_refs=review_refs,
            evidence_refs=evidence_refs,
            debate_transcript=transcript,
            outcome=outcome,
        )
        return ranked, match

    def _compare_debate_with_llm(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        reviews: list[Review],
        agent_feedback: list[str] | None = None,
    ) -> tuple[list[Hypothesis], Match]:
        response_text = self.llm_client.complete(
            _ranking_prompt(goal, first, second, reviews, agent_feedback),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(response_text, "debate ranking")
        winner_token = _clean_string(data.get("winner"), "tie").lower()
        if winner_token in {"first", first.id.lower()}:
            winner_hyp: Hypothesis | None = first
            loser_hyp: Hypothesis | None = second
        elif winner_token in {"second", second.id.lower()}:
            winner_hyp = second
            loser_hyp = first
        else:
            winner_hyp = None
            loser_hyp = None

        elo_before = {first.id: first.elo, second.id: second.elo}
        outcome = _clean_string(data.get("outcome"), "tie" if winner_hyp is None else "win")
        if winner_hyp is None or outcome == "tie":
            ranked = sorted([first, second], key=lambda item: item.id)
            winner = "tie"
            elo_after = dict(elo_before)
            outcome = "tie"
        else:
            winner_elo, loser_elo = update_elo(winner_hyp.elo, loser_hyp.elo)
            updated = {
                winner_hyp.id: winner_hyp.with_elo(winner_elo),
                loser_hyp.id: loser_hyp.with_elo(loser_elo),
            }
            ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
            winner = winner_hyp.id
            elo_after = {item.id: item.elo for item in ranked}
        review_refs = [review.id for review in reviews]
        evidence_refs = _unique_refs(
            [
                *first.evidence_refs,
                *second.evidence_refs,
                *(ref for review in reviews for ref in review.evidence_refs),
            ]
        )
        match = Match(
            id=stable_id("match", f"{goal.id}:llm-debate:{first.id}:{second.id}:{winner}:{response_text}"),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner,
            rationale=_clean_string(data.get("rationale"), "LLM debate judge compared the candidates."),
            elo_before=elo_before,
            elo_after=elo_after,
            comparison_mode="llm_debate_judge",
            judge_trace=_clean_string(data.get("judge_trace"), "llm debate judge returned structured JSON."),
            uncertainty=_bounded_float(data.get("uncertainty"), 0.5),
            review_refs=review_refs,
            evidence_refs=evidence_refs,
            debate_transcript=_string_list(data.get("debate_transcript"), []),
            outcome=outcome,
        )
        return ranked, match

    def _compare_multi_round_debate_with_llm(
        self,
        goal: ResearchGoal,
        first: Hypothesis,
        second: Hypothesis,
        reviews: list[Review],
        rounds: int,
        agent_feedback: list[str] | None = None,
    ) -> tuple[list[Hypothesis], Match]:
        transcript: list[str] = []
        for round_index in range(1, rounds + 1):
            response_text = self.llm_client.complete(
                _multi_round_debate_round_prompt(goal, first, second, reviews, round_index, rounds, transcript),
                max_tokens=self.llm_max_tokens,
            )
            data = _json_object(response_text, f"multi-round debate round {round_index}")
            transcript.extend(
                _string_list(
                    data.get("debate_transcript"),
                    _string_list(data.get("lines"), []),
                )
            )

        response_text = self.llm_client.complete(
            _multi_round_debate_judge_prompt(goal, first, second, reviews, transcript, rounds, agent_feedback),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(response_text, "multi-round debate final judge")
        winner_token = _clean_string(data.get("winner"), "tie").lower()
        if winner_token in {"first", first.id.lower()}:
            winner_hyp: Hypothesis | None = first
            loser_hyp: Hypothesis | None = second
        elif winner_token in {"second", second.id.lower()}:
            winner_hyp = second
            loser_hyp = first
        else:
            winner_hyp = None
            loser_hyp = None

        elo_before = {first.id: first.elo, second.id: second.elo}
        outcome = _clean_string(data.get("outcome"), "tie" if winner_hyp is None else "win")
        if winner_hyp is None or outcome == "tie":
            ranked = sorted([first, second], key=lambda item: item.id)
            winner = "tie"
            elo_after = dict(elo_before)
            outcome = "tie"
        else:
            winner_elo, loser_elo = update_elo(winner_hyp.elo, loser_hyp.elo)
            updated = {
                winner_hyp.id: winner_hyp.with_elo(winner_elo),
                loser_hyp.id: loser_hyp.with_elo(loser_elo),
            }
            ranked = sorted([updated[first.id], updated[second.id]], key=lambda item: item.elo, reverse=True)
            winner = winner_hyp.id
            elo_after = {item.id: item.elo for item in ranked}

        final_lines = _string_list(data.get("debate_transcript"), [])
        transcript = [*transcript, *final_lines]
        review_refs = [review.id for review in reviews]
        evidence_refs = _unique_refs(
            [
                *first.evidence_refs,
                *second.evidence_refs,
                *(ref for review in reviews for ref in review.evidence_refs),
            ]
        )
        match = Match(
            id=stable_id(
                "match",
                f"{goal.id}:llm-multi-round-debate:{rounds}:{first.id}:{second.id}:{winner}:{response_text}",
            ),
            hypothesis_a=first.id,
            hypothesis_b=second.id,
            winner=winner,
            rationale=_clean_string(data.get("rationale"), "LLM multi-round debate judge compared the candidates."),
            elo_before=elo_before,
            elo_after=elo_after,
            comparison_mode="llm_multi_round_debate_judge",
            judge_trace=(
                f"multi_round_debate rounds={rounds}; "
                f"{_clean_string(data.get('judge_trace'), 'llm multi-round debate judge returned structured JSON.')}"
            ),
            uncertainty=_bounded_float(data.get("uncertainty"), 0.5),
            review_refs=review_refs,
            evidence_refs=evidence_refs,
            debate_transcript=transcript,
            outcome=outcome,
        )
        return ranked, match


class EvolutionAgent(_LLMTraceMixin):
    def __init__(self, llm_client: Any | None = None, llm_max_tokens: int = 1024) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens

    def evolve(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback: list[str],
        limit: int = 2,
        evidence_store: EvidenceStore | None = None,
    ) -> list[Hypothesis]:
        if self.llm_client:
            try:
                return self._evolve_with_llm(goal, parents, feedback, limit, evidence_store)
            except LLMResponseError:
                pass
        return self._evolve_deterministic(
            goal,
            parents,
            feedback,
            strategy="simplification",
            limit=limit,
            evidence_store=evidence_store,
            origin="evolution",
        )

    def evolve_with_strategy(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback: list[str],
        strategy: str,
        limit: int = 2,
        evidence_store: EvidenceStore | None = None,
    ) -> list[Hypothesis]:
        strategy_key = self._normalize_strategy(strategy)
        if self.llm_client:
            try:
                strategy_feedback = [f"Evolution strategy: {strategy_key}", *feedback]
                children = self._evolve_with_llm(
                    goal,
                    parents,
                    strategy_feedback,
                    limit,
                    evidence_store,
                )
                return [
                    replace(
                        child,
                        id=stable_id("hyp", f"{child.id}:{strategy_key}"),
                        origin=f"evolution:{strategy_key}",
                    )
                    for child in children
                ]
            except LLMResponseError:
                pass
        return self._evolve_deterministic(
            goal,
            parents,
            feedback,
            strategy=strategy_key,
            limit=limit,
            evidence_store=evidence_store,
            origin=f"evolution:{strategy_key}",
        )

    def _evolve_deterministic(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback: list[str],
        strategy: str,
        limit: int,
        evidence_store: EvidenceStore | None,
        origin: str,
    ) -> list[Hypothesis]:
        children: list[Hypothesis] = []
        for parent_group in self._parent_groups_for_strategy(parents, strategy, limit):
            parent = parent_group[0]
            parent_ids = [item.id for item in parent_group]
            parent_titles = " + ".join(item.title for item in parent_group)
            feedback_text = "; ".join(feedback) if feedback else "tighten evidence and reduce evaluation cost"
            retrieved_refs, retrieval_note, evolution_trace = self._evolution_retrieval_trace(
                goal,
                parent_group,
                feedback_text,
                strategy,
                evidence_store,
            )
            title = self._strategy_title(strategy, parent_group)
            claim = self._strategy_claim(strategy, parent_group)
            rationale = self._strategy_rationale(
                strategy,
                parent_titles,
                feedback_text,
                retrieval_note,
            )
            child = Hypothesis(
                id=self._strategy_child_id(goal, strategy, parent_ids, feedback_text, origin),
                title=title,
                claim=claim,
                rationale=rationale,
                assumptions=self._strategy_assumptions(strategy, parent_group),
                evidence_refs=_unique_refs(
                    [
                        *(ref for item in parent_group for ref in item.evidence_refs),
                        *retrieved_refs,
                    ]
                ),
                test_plan=TestPlan(
                    experiment=self._strategy_experiment(strategy, parent_group),
                    metrics=parent.test_plan.metrics,
                    success_condition=self._strategy_success_condition(strategy),
                ),
                risks=self._strategy_risks(strategy, parent_group),
                origin=origin,
                parent_ids=parent_ids,
                evolution_trace=evolution_trace,
            )
            children.append(child)
        return children

    def _evolution_retrieval_trace(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback_text: str,
        strategy: str,
        evidence_store: EvidenceStore | None,
    ) -> tuple[list[str], str, list[str]]:
        parent_mechanism_query = " ".join(
            [
                *(item.title for item in parents),
                *(item.claim for item in parents),
                *(item.rationale for item in parents),
            ]
        )
        feedback_query = " ".join(
            [
                feedback_text,
                *(risk for item in parents for risk in item.risks),
                *(assumption for item in parents for assumption in item.assumptions),
            ]
        )
        strategy_query = " ".join(
            [
                strategy.replace("_", " "),
                goal.objective,
                *(metric for item in parents for metric in item.test_plan.metrics),
                *(item.test_plan.success_condition for item in parents),
            ]
        )
        turns = [
            ("parent mechanisms", parent_mechanism_query),
            ("feedback constraints", feedback_query),
            ("strategy grounding", strategy_query),
        ]
        retrieved_refs: list[str] = []
        citations: list[str] = []
        evolution_trace: list[str] = []
        for index, (label, query) in enumerate(turns, start=1):
            bundle = evidence_store.retrieve(query, limit=3) if evidence_store else None
            turn_refs = bundle.evidence_refs if bundle else []
            retrieved_refs.extend(turn_refs)
            citations.extend(bundle.citations if bundle else [])
            evolution_trace.append(f"Turn {index} query ({label}): {query}")
            evolution_trace.append(f"Turn {index} evidence: {', '.join(turn_refs) or 'none'}")
            if bundle:
                for item in bundle.evidence[:2]:
                    evolution_trace.append(
                        f"Turn {index} observation: {item.id} {item.kind} from {item.source}: "
                        f"{_truncate(item.content, 180)}"
                    )
        unique_refs = _unique_refs(retrieved_refs)
        unique_citations = _unique_refs(citations)
        evolution_trace.append(
            f"Evolution assessment: strategy={strategy}; parents={', '.join(item.id for item in parents)}; "
            f"retrieved evidence={len(unique_refs)}."
        )
        retrieval_note = f" Retrieved evidence: {'; '.join(unique_citations[:2])}." if unique_citations else ""
        return unique_refs, retrieval_note, evolution_trace

    def _parent_groups_for_strategy(
        self,
        parents: list[Hypothesis],
        strategy: str,
        limit: int,
    ) -> list[list[Hypothesis]]:
        if limit <= 0 or not parents:
            return []
        if strategy == "combination" and len(parents) > 1:
            groups: list[list[Hypothesis]] = []
            for index in range(min(limit, len(parents) - 1)):
                groups.append([parents[index], parents[index + 1]])
            return groups
        return [[parent] for parent in parents[:limit]]

    def _strategy_child_id(
        self,
        goal: ResearchGoal,
        strategy: str,
        parent_ids: list[str],
        feedback_text: str,
        origin: str,
    ) -> str:
        if strategy == "simplification" and origin == "evolution" and len(parent_ids) == 1:
            return stable_id("hyp", f"{goal.id}:{parent_ids[0]}:simplified:{feedback_text}")
        return stable_id("hyp", f"{goal.id}:{strategy}:{','.join(parent_ids)}:{feedback_text}")

    def _strategy_title(self, strategy: str, parents: list[Hypothesis]) -> str:
        parent = parents[0]
        if strategy == "simplification":
            return f"Simplified {parent.title}"
        if strategy == "feasibility_improvement":
            return f"Feasibility-focused {parent.title}"
        if strategy == "evidence_grounding":
            return f"Evidence-grounded {parent.title}"
        if strategy == "feedback_grounding":
            return f"Feedback-grounded {parent.title}"
        if strategy == "combination" and len(parents) > 1:
            return f"Combined {parents[0].title} + {parents[1].title}"
        if strategy == "analogy":
            return f"Analogical {parent.title}"
        if strategy in {"divergent_thinking", "out_of_box_divergence"}:
            return f"Divergent {parent.title}"
        return f"{strategy.replace('_', ' ').title()} {parent.title}"

    def _strategy_claim(self, strategy: str, parents: list[Hypothesis]) -> str:
        parent = parents[0]
        if strategy == "simplification":
            return f"{parent.claim} A simplified variant should reduce cost and make evaluation easier."
        if strategy == "feasibility_improvement":
            return (
                f"{parent.claim} A feasibility-focused variant should lower validation cost, "
                "sharpen constraints, and define a lower-cost evaluation path."
            )
        if strategy == "evidence_grounding":
            return (
                f"{parent.claim} Retrieved evidence should constrain this variant's "
                "mechanism, assumptions, and evaluation claims."
            )
        if strategy == "feedback_grounding":
            return (
                f"{parent.claim} A feedback-grounded variant should convert reviewer feedback "
                "into narrower assumptions and explicit acceptance criteria."
            )
        if strategy == "combination" and len(parents) > 1:
            return (
                f"A combined variant linking {parents[0].title} and {parents[1].title} "
                "should cover complementary failure modes while sharing one benchmark gate."
            )
        if strategy == "analogy":
            return (
                f"{parent.claim} An analogical variant should transfer the same control "
                "pattern to a different coding-agent failure mode."
            )
        if strategy in {"divergent_thinking", "out_of_box_divergence"}:
            return (
                f"{parent.claim} A divergent variant should test a less obvious mechanism "
                "while keeping the benchmark measurable."
            )
        return f"{parent.claim} A {strategy.replace('_', ' ')} variant should be tested separately."

    def _strategy_rationale(
        self,
        strategy: str,
        parent_titles: str,
        feedback_text: str,
        retrieval_note: str,
    ) -> str:
        if strategy == "simplification":
            return f"Derived from {parent_titles}; meta-review feedback: {feedback_text}.{retrieval_note}"
        strategy_label = strategy.replace("_", " ")
        return (
            f"Derived from {parent_titles} using {strategy_label}; "
            f"meta-review feedback: {feedback_text}.{retrieval_note}"
        )

    def _strategy_assumptions(self, strategy: str, parents: list[Hypothesis]) -> list[str]:
        assumptions = [assumption for parent in parents for assumption in parent.assumptions]
        additions = {
            "simplification": "The simplified variant preserves the core mechanism.",
            "feasibility_improvement": "A cheaper validation path can still detect meaningful regressions.",
            "evidence_grounding": "Retrieved evidence is relevant enough to constrain the evolved mechanism.",
            "feedback_grounding": "Reviewer feedback identifies the highest-risk assumption to narrow.",
            "combination": "The combined mechanisms address complementary failure modes.",
            "analogy": "The parent control pattern transfers to a related failure mode.",
            "divergent_thinking": "The divergent mechanism remains measurable with available benchmarks.",
            "out_of_box_divergence": "The divergent mechanism remains measurable with available benchmarks.",
        }
        return _unique_refs([*assumptions, additions.get(strategy, "The strategy preserves testability.")])

    def _strategy_experiment(self, strategy: str, parents: list[Hypothesis]) -> str:
        parent_titles = " + ".join(parent.title for parent in parents)
        if strategy == "simplification":
            return f"Compare baseline, parent idea, and simplified variant for: {parent_titles}."
        if strategy == "feasibility_improvement":
            return f"Compare {parent_titles} against a feasibility-focused low-cost benchmark variant."
        if strategy == "evidence_grounding":
            return f"Compare {parent_titles} against an evidence-grounded cited variant."
        if strategy == "feedback_grounding":
            return f"Replay reviewer feedback and compare {parent_titles} against the grounded variant."
        if strategy == "combination":
            return f"Compare each parent and the combined variant for: {parent_titles}."
        if strategy == "analogy":
            return f"Test whether an analogical transfer of {parent_titles} works on a related task family."
        if strategy in {"divergent_thinking", "out_of_box_divergence"}:
            return f"Compare {parent_titles} with a divergent mechanism on the same benchmark suite."
        return f"Compare {parent_titles} against a {strategy.replace('_', ' ')} variant."

    def _strategy_success_condition(self, strategy: str) -> str:
        if strategy == "simplification":
            return "Simplified variant keeps reliability gains while reducing cost or complexity."
        if strategy == "feasibility_improvement":
            return "Variant preserves reliability signals while reducing validation cost or latency."
        if strategy == "evidence_grounding":
            return "Variant cites retrieved evidence and preserves or improves target benchmark metrics."
        if strategy == "feedback_grounding":
            return "Variant resolves cited review weaknesses without lowering benchmark performance."
        if strategy == "combination":
            return "Combined variant outperforms each parent or explains a measurable tradeoff."
        if strategy == "analogy":
            return "Analogical variant improves a related task without losing parent-task performance."
        if strategy in {"divergent_thinking", "out_of_box_divergence"}:
            return "Divergent variant produces a measurable gain not explained by parent mechanisms."
        return "Strategy-specific variant improves at least one target metric without new safety failures."

    def _strategy_risks(self, strategy: str, parents: list[Hypothesis]) -> list[str]:
        risks = [risk for parent in parents for risk in parent.risks]
        additions = {
            "simplification": "simplification may remove the useful mechanism",
            "feasibility_improvement": "feasibility improvements may over-optimize for cheap proxies",
            "evidence_grounding": "retrieved evidence may be incomplete or misleading",
            "feedback_grounding": "feedback grounding may overfit to a single review",
            "combination": "combination may add complexity without additive gains",
            "analogy": "analogy may transfer the wrong causal mechanism",
            "divergent_thinking": "divergent idea may be hard to compare fairly",
            "out_of_box_divergence": "divergent idea may be hard to compare fairly",
        }
        return _unique_refs([*risks, additions.get(strategy, "strategy may introduce unmeasured tradeoffs")])

    def _normalize_strategy(self, strategy: str) -> str:
        normalized = strategy.strip().lower().replace("-", "_") if strategy else "simplification"
        if normalized in {"combine", "recombination"}:
            return "combination"
        if normalized in {"feasibility", "feasibility_refinement"}:
            return "feasibility_improvement"
        if normalized in {"grounding", "grounded_evolution", "evidence_grounded", "literature_grounding"}:
            return "evidence_grounding"
        if normalized in {"feedback", "review_feedback"}:
            return "feedback_grounding"
        return normalized

    def _evolve_with_llm(
        self,
        goal: ResearchGoal,
        parents: list[Hypothesis],
        feedback: list[str],
        limit: int,
        evidence_store: EvidenceStore | None,
    ) -> list[Hypothesis]:
        evidence = []
        if evidence_store and parents:
            evidence = evidence_store.retrieve(" ".join(parent.title for parent in parents), limit=5).evidence
        response_text = self.llm_client.complete(
            _evolution_prompt(goal, parents, feedback, evidence, limit),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(response_text, "evolution")
        raw_hypotheses = data.get("hypotheses")
        if not isinstance(raw_hypotheses, list):
            raise LLMResponseError("LLM evolution response must include a hypotheses list.")
        children: list[Hypothesis] = []
        parent_ids = [parent.id for parent in parents]
        parent_metrics = parents[0].test_plan.metrics if parents else goal.metrics
        for raw in raw_hypotheses[:limit]:
            if not isinstance(raw, dict):
                continue
            title = _clean_string(raw.get("title"), "LLM evolved hypothesis")
            claim = _clean_string(raw.get("claim"), "An evolved coding-agent workflow can improve measured reliability.")
            rationale = _clean_string(raw.get("rationale"), "LLM evolution combined parent mechanisms and feedback.")
            assumptions = _string_list(raw.get("assumptions"), ["The evolved mechanism preserves useful parent behavior."])
            risks = _string_list(raw.get("risks"), ["LLM-evolved hypothesis needs human review before implementation."])
            evidence_refs = _string_list(raw.get("evidence_refs"), [item.id for item in evidence])
            evolution_trace = _string_list(raw.get("evolution_trace"), [])
            child = Hypothesis(
                id=stable_id("hyp", f"{goal.id}:llm_evolution:{','.join(parent_ids)}:{title}:{claim}"),
                title=title,
                claim=claim,
                rationale=rationale,
                assumptions=assumptions,
                evidence_refs=evidence_refs,
                test_plan=TestPlan(
                    experiment=f"Compare parent workflow variants against evolved idea: {title}.",
                    metrics=parent_metrics,
                    success_condition="Evolved variant improves benchmark outcome without unacceptable safety or cost tradeoffs.",
                ),
                risks=risks,
                origin="llm_evolution",
                parent_ids=parent_ids,
                evolution_trace=evolution_trace,
            )
            children.append(child)
        return children


class MetaReviewAgent(_LLMTraceMixin):
    def __init__(self, llm_client: Any | None = None, llm_max_tokens: int = 1024) -> None:
        self._init_llm_trace(llm_client)
        self.llm_max_tokens = llm_max_tokens

    def summarize(
        self,
        goal: ResearchGoal,
        reviews: list[Review],
        matches: list[Match],
        evidence_store: EvidenceStore | None = None,
    ) -> MetaReview:
        if self.llm_client:
            try:
                return self._summarize_with_llm(goal, reviews, matches, evidence_store)
            except LLMResponseError:
                pass
        weakness_counts = Counter(weakness for review in reviews for weakness in review.weaknesses)
        safety_counts = Counter(note for review in reviews for note in review.safety_notes)
        common_weaknesses = [item for item, _count in weakness_counts.most_common(5)]
        if not common_weaknesses:
            common_weaknesses = ["needs measured benchmark evidence before claiming improvement"]
        evidence_refs: list[str] = []
        retrieval_feedback: list[str] = []
        if evidence_store:
            bundle = evidence_store.retrieve(
                " ".join(
                    [
                        goal.objective,
                        "benchmark deltas repo-specific failure examples novelty review",
                    ]
                ),
                limit=3,
            )
            evidence_refs = bundle.evidence_refs
            if bundle.citations:
                retrieval_feedback.append(
                    f"Retrieved evidence should ground the next generation: {'; '.join(bundle.citations[:2])}."
                )
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
            agent_feedback={
                "generation": [
                    "Prefer hypotheses that cite local evidence and name the smallest useful experiment.",
                    *retrieval_feedback,
                ],
                "reflection": [
                    "Separate initial plausibility checks from grounded contradiction checks."
                ],
                "ranking": [
                    "Treat Elo as a scheduling signal until benchmark outcomes calibrate it."
                ],
            },
            evidence_refs=evidence_refs,
        )

    def _summarize_with_llm(
        self,
        goal: ResearchGoal,
        reviews: list[Review],
        matches: list[Match],
        evidence_store: EvidenceStore | None,
    ) -> MetaReview:
        evidence = []
        if evidence_store:
            evidence = evidence_store.retrieve(goal.objective, limit=5).evidence
        response_text = self.llm_client.complete(
            _meta_review_prompt(goal, reviews, matches, evidence),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(response_text, "meta-review")
        raw_agent_feedback = data.get("agent_feedback")
        agent_feedback: dict[str, list[str]] = {}
        if isinstance(raw_agent_feedback, dict):
            for key, value in raw_agent_feedback.items():
                if isinstance(key, str):
                    agent_feedback[key] = _string_list(value, [])
        if not agent_feedback:
            agent_feedback = {"generation": ["Ground future hypotheses in explicit evidence."]}
        return MetaReview(
            id=stable_id("meta", f"{goal.id}:llm:{len(reviews)}:{len(matches)}:{response_text}"),
            common_weaknesses=_string_list(
                data.get("common_weaknesses"),
                ["needs measured benchmark evidence before claiming improvement"],
            ),
            safety_concerns=_string_list(data.get("safety_concerns"), []),
            missing_evidence=_string_list(data.get("missing_evidence"), ["benchmark deltas"]),
            promising_directions=_string_list(data.get("promising_directions"), ["evaluation design"]),
            prompt_feedback=_string_list(data.get("prompt_feedback"), ["Require evidence-backed hypotheses."]),
            agent_feedback=agent_feedback,
            evidence_refs=_string_list(data.get("evidence_refs"), [item.id for item in evidence]),
        )

    def build_overview(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        meta_reviews: list[MetaReview],
        cycle: int,
    ) -> ResearchOverview:
        if self.llm_client:
            try:
                return self._build_overview_with_llm(goal, hypotheses, meta_reviews, cycle)
            except LLMResponseError:
                pass
        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:3]
        latest_meta = meta_reviews[-1] if meta_reviews else None
        directions = (
            latest_meta.promising_directions
            if latest_meta
            else ["critic loops", "evaluation design", "memory freshness"]
        )
        next_experiments = [
            f"Test {item.title} with metrics: {', '.join(item.test_plan.metrics)}"
            for item in leaders
        ]
        if not next_experiments:
            next_experiments = ["Generate at least one accepted hypothesis before experiment selection."]
        missing_evidence = latest_meta.missing_evidence if latest_meta else ["benchmark deltas"]
        limitations = [
            "Elo is an internal proxy until calibrated against benchmark or human outcomes.",
            *missing_evidence,
        ]
        leader_titles = ", ".join(item.title for item in leaders) if leaders else "no accepted hypotheses yet"
        return ResearchOverview(
            id=stable_id("overview", f"{goal.id}:{cycle}:{','.join(item.id for item in leaders)}"),
            summary=(
                f"Cycle {cycle} overview for {goal.objective}: current leaders emphasize "
                f"{leader_titles}."
            ),
            top_hypothesis_ids=[item.id for item in leaders],
            promising_directions=directions,
            next_experiments=next_experiments,
            limitations=limitations,
            generated_by="meta_review",
        )

    def build_research_output_artifacts(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        meta_reviews: list[MetaReview],
        overview: ResearchOverview | None,
        cycle: int,
    ) -> list[ResearchOutputArtifact]:
        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:3]
        if not leaders:
            return []
        primary = leaders[0]
        latest_meta = meta_reviews[-1] if meta_reviews else None
        evidence_refs = _unique_refs([
            *primary.evidence_refs,
            *((latest_meta.evidence_refs if latest_meta else []) or []),
        ])
        directions = (
            overview.promising_directions
            if overview
            else (latest_meta.promising_directions if latest_meta else ["evaluation design"])
        )
        missing_evidence = latest_meta.missing_evidence if latest_meta else ["external benchmark validation"]
        contact_targets = _contact_targets_for_output(goal, primary, evidence_refs)
        publication = ResearchOutputArtifact(
            id=stable_id("output", f"{goal.id}:{cycle}:publication:{primary.id}"),
            output_type="publication_brief",
            title=f"Publication brief: {primary.title}",
            summary=f"Paper-style summary for {primary.title}.",
            sections={
                "abstract": primary.claim,
                "contribution": primary.rationale,
                "methods": primary.test_plan.experiment,
                "evaluation": (
                    f"Measure {', '.join(primary.test_plan.metrics)}; success condition: "
                    f"{primary.test_plan.success_condition}"
                ),
                "limitations": "; ".join(missing_evidence),
            },
            related_hypothesis_ids=[primary.id],
            contact_targets=[],
            evidence_refs=evidence_refs,
        )
        grant = ResearchOutputArtifact(
            id=stable_id("output", f"{goal.id}:{cycle}:grant:{primary.id}"),
            output_type="grant_brief",
            title=f"Grant brief: {primary.title}",
            summary=f"Grant-style aims and evaluation plan for {goal.objective}.",
            sections={
                "specific_aims": "; ".join(directions[:3]) or primary.claim,
                "significance": primary.rationale,
                "approach": primary.test_plan.experiment,
                "milestones": "Prototype the workflow, run benchmark comparison, and audit regressions.",
                "evaluation": f"Primary metrics: {', '.join(primary.test_plan.metrics)}.",
            },
            related_hypothesis_ids=[item.id for item in leaders],
            contact_targets=contact_targets,
            evidence_refs=evidence_refs,
        )
        contacts = ResearchOutputArtifact(
            id=stable_id("output", f"{goal.id}:{cycle}:contacts:{primary.id}:{','.join(contact_targets)}"),
            output_type="contact_suggestions",
            title=f"Contact suggestions: {primary.title}",
            summary="Suggested human or project contacts for external validation and collaboration.",
            sections={
                "validation_targets": "; ".join(contact_targets),
                "reason": "The paper's co-scientist loop expects human expert selection and external validation.",
                "request": "Ask contacts to review novelty, benchmark fit, implementation feasibility, and safety boundaries.",
            },
            related_hypothesis_ids=[item.id for item in leaders],
            contact_targets=contact_targets,
            evidence_refs=evidence_refs,
        )
        return [publication, grant, contacts]

    def _build_overview_with_llm(
        self,
        goal: ResearchGoal,
        hypotheses: list[Hypothesis],
        meta_reviews: list[MetaReview],
        cycle: int,
    ) -> ResearchOverview:
        response_text = self.llm_client.complete(
            _overview_prompt(goal, hypotheses, meta_reviews, cycle),
            max_tokens=self.llm_max_tokens,
        )
        data = _json_object(response_text, "research overview")
        leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:3]
        return ResearchOverview(
            id=stable_id("overview", f"{goal.id}:llm:{cycle}:{response_text}"),
            summary=_clean_string(data.get("summary"), f"Cycle {cycle} LLM overview for {goal.objective}."),
            top_hypothesis_ids=_string_list(
                data.get("top_hypothesis_ids"),
                [item.id for item in leaders],
            ),
            promising_directions=_string_list(data.get("promising_directions"), ["evaluation design"]),
            next_experiments=_string_list(
                data.get("next_experiments"),
                [f"Test {item.title} with metrics: {', '.join(item.test_plan.metrics)}" for item in leaders],
            ),
            limitations=_string_list(
                data.get("limitations"),
                ["Human validation is still required."],
            ),
            generated_by="llm_meta_review",
        )


def _tokens(text: str) -> list[str]:
    return [token.strip(".,:;()[]{}").lower() for token in text.split() if len(token.strip(".,:;()[]{}")) > 2]


def _plan_agent_retrieval(
    *,
    llm_client: Any | None,
    llm_max_tokens: int,
    agent: str,
    goal: ResearchGoal,
    available_tools: list[str],
    subject: str,
    iteration: int,
    observations: list[Evidence],
    agent_feedback: list[str] | None,
) -> list[AgentRetrievalRequest]:
    allowed_search = [
        tool
        for tool in ("literature_search", "web_search", "repo_search")
        if tool in set(available_tools)
    ]
    eligible_source_refs: dict[str, list[str]] = {
        "web_document_fetch": [
            item.id
            for item in observations
            if item.kind == "web_search_result" and "web_document_fetch" in available_tools
        ],
        "literature_full_text_fetch": [
            item.id
            for item in observations
            if item.kind == "literature_search_result"
            and item.metadata.get("full_text_url")
            and "literature_full_text_fetch" in available_tools
        ],
    }
    eligible_source_refs = {
        tool: refs for tool, refs in eligible_source_refs.items() if refs
    }
    allowed = [*allowed_search, *eligible_source_refs]
    if not allowed:
        return []
    observation_lines = [
        f"- {item.id} from {item.source}: {_truncate(item.content, 240)}"
        for item in observations[:5]
    ]
    if llm_client is not None:
        prompt = f"""Agent-driven retrieval planning for the {agent} worker.
Research objective: {goal.objective}
{_goal_guidance_block(goal)}
Iteration: {iteration + 1}
Allowed tools: {', '.join(allowed)}

Current subject:
{_truncate(subject, 2400)}

Safe observations from earlier retrieval iterations:
{chr(10).join(observation_lines) or '- none yet'}

Eligible reference-bound fetches:
{chr(10).join(f'- {tool}: {", ".join(refs)}' for tool, refs in eligible_source_refs.items()) or '- none yet'}

Return only valid JSON with a `requests` array. A search request must contain an allowed search
tool, a focused `query`, and a rationale. A fetch request must contain an allowed fetch tool,
one exact eligible `source_ref`, and a rationale; omit the query. Return at most one request so
the next iteration can observe its result before refining the search. Never propose a URL,
filesystem path, shell command, crawl setting, or full-text setting.
{_feedback_block(agent_feedback)}"""
        try:
            data = _json_object(llm_client.complete(prompt, max_tokens=llm_max_tokens), "retrieval plan")
            parsed = _retrieval_requests_from_data(
                data.get("requests"),
                allowed,
                eligible_source_refs=eligible_source_refs,
            )
            if parsed:
                return parsed[:1]
        except LLMResponseError:
            pass

    if iteration > 0 and eligible_source_refs:
        tool = next(iter(eligible_source_refs))
        source_ref = eligible_source_refs[tool][0]
        return [
            AgentRetrievalRequest(
                tool=tool,
                query="",
                rationale="Inspect the full content of a safe result observed in the prior iteration.",
                source_ref=source_ref,
            )
        ]
    if not allowed_search:
        return []
    tool = allowed_search[iteration % len(allowed_search)]
    observation_terms = ""
    if observations:
        observation_terms = " ".join(sorted(_meaningful_terms(observations[-1].content))[:6])
    if agent == "reflection":
        suffix = (
            "contradictory evidence prior art benchmark failure"
            if iteration == 0
            else f"replication limitations counterevidence {observation_terms}"
        )
        rationale = "Independently verify novelty, assumptions, and failure modes before ranking."
    else:
        suffix = (
            "prior work benchmark limitations open problems"
            if iteration == 0
            else f"unexplored directions contradictory findings {observation_terms}"
        )
        rationale = "Ground proposal generation in prior evidence and unresolved limitations."
    query = " ".join([goal.objective, _truncate(subject, 220), suffix])
    return [AgentRetrievalRequest(tool=tool, query=query, rationale=rationale)]


def _retrieval_requests_from_data(
    value: Any,
    allowed_tools: list[str],
    *,
    eligible_source_refs: dict[str, list[str]] | None = None,
) -> list[AgentRetrievalRequest]:
    if not isinstance(value, list):
        return []
    requests: list[AgentRetrievalRequest] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        tool = _clean_string(raw.get("tool"), "")
        query = _clean_string(raw.get("query"), "")
        source_ref = _clean_string(raw.get("source_ref"), "")
        rationale = _clean_string(raw.get("rationale"), "Agent requested governed evidence retrieval.")
        if tool not in allowed_tools:
            continue
        if tool in {"web_document_fetch", "literature_full_text_fetch"}:
            eligible_refs = set((eligible_source_refs or {}).get(tool, []))
            if not source_ref or source_ref not in eligible_refs:
                continue
            requests.append(
                AgentRetrievalRequest(
                    tool=tool,
                    query="",
                    rationale=rationale,
                    source_ref=source_ref,
                )
            )
            continue
        if not query:
            continue
        requests.append(AgentRetrievalRequest(tool=tool, query=query, rationale=rationale))
    return requests


def _json_object(response_text: str, context: str) -> dict[str, Any]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM {context} response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMResponseError(f"LLM {context} response must be a JSON object.")
    return data


def _llm_turn_label(prompt: str) -> str:
    lowered = prompt.lower()
    patterns = [
        ("configuring a coding-agent ai co-scientist research plan", "research plan"),
        ("safety critic", "safety critic"),
        ("testable hypotheses", "hypothesis generation"),
        ("generation turn 1 debate proposal", "generation debate proposal"),
        ("generation turn 2 debate critique", "generation debate critique"),
        ("generation turn 3 debate synthesis", "generation debate synthesis"),
        ("tool-augmented generation turn 1", "tool query plan"),
        ("tool-augmented generation turn 2", "tool observation"),
        ("tool-augmented generation turn 3", "tool synthesis"),
        ("reflection turn 1 claim mechanism", "deep verification mechanism"),
        ("reflection turn 2 assumption risk audit", "deep verification risk audit"),
        ("reflection turn 3 benchmark validation synthesis", "deep verification synthesis"),
        ("red-team autonomy", "safety autonomy red team"),
        ("red-team data exposure", "safety source red team"),
        ("red-team synthesis", "safety synthesis"),
        ("scientific reflection agent", "reflection review"),
        ("proximity turn 1 semantic neighborhood mapping", "proximity neighborhood"),
        ("proximity turn 2 evidence and review overlap", "proximity overlap"),
        ("proximity turn 3 clustering synthesis", "proximity synthesis"),
        ("pairwise debate judge", "ranking debate judge"),
        ("multi-round debate round", "ranking debate round"),
        ("multi-round debate final judge", "ranking final judge"),
        ("evolution agent", "evolution synthesis"),
        ("meta-review agent", "meta-review synthesis"),
        ("research overview", "research overview"),
        ("generate", "hypothesis generation"),
    ]
    for needle, label in patterns:
        if needle in lowered:
            return label
    return "llm completion"


def _clean_string(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned or fallback


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    parsed = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return parsed or list(fallback)


def _int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        try:
            parsed[key] = int(raw)
        except (TypeError, ValueError):
            continue
    return parsed


def _bounded_float(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return round(min(max(number, 0.0), 1.0), 3)


def _match_summary_line(hypothesis: Hypothesis, matches: list[Match] | None) -> str:
    record = [m for m in (matches or []) if hypothesis.id in (m.hypothesis_a, m.hypothesis_b)]
    if not record:
        return ""
    wins = sum(1 for m in record if m.winner == hypothesis.id)
    losses = sum(1 for m in record if m.winner not in ("", "tie", hypothesis.id))
    ties = sum(1 for m in record if m.winner == "tie")
    return (
        f"\nTournament match record: won {wins}, lost {losses}, and tied {ties} "
        f"of {len(record)} matches.\n"
    )


def _review_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    review_type: str,
    evidence: list[Any],
    agent_feedback: list[str] | None = None,
    matches: list[Match] | None = None,
) -> str:
    evidence_text = _evidence_prompt_lines(evidence)
    return f"""You are a scientific reflection agent for a coding-agent AI co-scientist.
Review type: {review_type}
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
- id: {hypothesis.id}
- title: {hypothesis.title}
- claim: {hypothesis.claim}
- rationale: {hypothesis.rationale}
- assumptions: {'; '.join(hypothesis.assumptions)}
- risks: {'; '.join(hypothesis.risks)}

Evidence:
{evidence_text}
{_match_summary_line(hypothesis, matches)}
{_review_mode_instruction(review_type)}
Return only valid JSON with:
decision, scores, strengths, weaknesses, safety_notes, findings, confidence, requires_revision, evidence_refs.
{_feedback_block(agent_feedback)}"""


def _review_mode_instruction(review_type: str) -> str:
    if review_type == "observation_review":
        return (
            "Compare every observation separately with the hypothesis prediction. For each one, "
            "state supports, contradicts, or inconclusive and explain the causal mismatch."
        )
    if review_type == "simulation_review":
        return (
            "Reason step by step through mechanism, intervention, expected measurements, each "
            "simulated outcome, and explicit failure conditions before deciding."
        )
    return ""


def _llm_reflection_mechanism_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
) -> str:
    return f"""Reflection turn 1 claim mechanism for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Analyze the causal mechanism and what evidence would need to support it. Do not finalize JSON yet."""


def _llm_reflection_risk_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
    mechanism_text: str,
) -> str:
    return f"""Reflection turn 2 assumption risk audit for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Turn 1 mechanism analysis:
{_truncate(mechanism_text, 2200)}

Decompose every explicit assumption into independently testable sub-assumptions. Evaluate each
against the evidence, distinguish fundamental failures from repairable details, and return only
valid JSON with an `assumption_checks` array. Every item must contain: assumption,
parent_assumption, depth, verdict (supported, contradicted, or uncertain), fundamental,
invalidates_hypothesis, evidence_refs, and reasoning. Do not write the final review yet."""


def _llm_reflection_benchmark_synthesis_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
    mechanism_text: str,
    risk_text: str,
    agent_feedback: list[str] | None = None,
) -> str:
    return f"""Reflection turn 3 benchmark validation synthesis for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Turn 1 mechanism analysis:
{_truncate(mechanism_text, 1400)}

Turn 2 assumption/risk audit:
{_truncate(risk_text, 1800)}

Return only valid JSON with:
decision, scores, strengths, weaknesses, safety_notes, findings, confidence, requires_revision,
evidence_refs, assumption_checks.
Preserve the assumption checks from turn 2. A contradicted fundamental assumption must reject
the hypothesis; a contradicted non-fundamental assumption must require revision. Focus on
benchmark validation and whether revision is required before ranking or external study.{_feedback_block(agent_feedback)}"""


def _llm_reflection_autonomy_safety_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
) -> str:
    return f"""Reflection turn 1 autonomy and deployment red team for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Red-team autonomy, deployment, repo mutation, and human approval boundaries. Do not finalize JSON yet."""


def _llm_reflection_source_safety_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
    autonomy_text: str,
) -> str:
    return f"""Reflection turn 2 data and source-injection red team for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Turn 1 autonomy/deployment red team:
{_truncate(autonomy_text, 1800)}

Red-team data exposure, credential leakage, prompt injection, source injection, and benchmark gaming. Do not finalize JSON yet."""


def _llm_reflection_safety_synthesis_prompt(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence: list[Any],
    autonomy_text: str,
    source_text: str,
    agent_feedback: list[str] | None = None,
) -> str:
    return f"""Reflection turn 3 safety synthesis for a coding-agent AI co-scientist worker.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypothesis:
{_hypothesis_prompt_text(hypothesis)}

Evidence:
{_evidence_prompt_lines(evidence)}

Turn 1 autonomy/deployment red team:
{_truncate(autonomy_text, 1200)}

Turn 2 data/source-injection red team:
{_truncate(source_text, 1800)}

Return only valid JSON with:
decision, scores, strengths, weaknesses, safety_notes, findings, confidence, requires_revision, evidence_refs.
Focus on safety gating, source-injection mitigation, and whether revision is required.{_feedback_block(agent_feedback)}"""


def _hypothesis_prompt_text(hypothesis: Hypothesis) -> str:
    return "\n".join(
        [
            f"- id: {hypothesis.id}",
            f"- title: {hypothesis.title}",
            f"- claim: {hypothesis.claim}",
            f"- rationale: {hypothesis.rationale}",
            f"- assumptions: {'; '.join(hypothesis.assumptions)}",
            f"- risks: {'; '.join(hypothesis.risks)}",
        ]
    )


def _ranking_prompt(
    goal: ResearchGoal,
    first: Hypothesis,
    second: Hypothesis,
    reviews: list[Review],
    agent_feedback: list[str] | None = None,
) -> str:
    review_lines = "\n".join(
        f"- {review.id} for {review.hypothesis_id}: {review.decision}; "
        f"strengths={'; '.join(review.strengths)}; weaknesses={'; '.join(review.weaknesses)}"
        for review in reviews
    ) or "- No reviews available."
    return f"""You are a pairwise debate judge for a coding-agent AI co-scientist.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

First candidate:
- id: {first.id}
- title: {first.title}
- claim: {first.claim}

Second candidate:
- id: {second.id}
- title: {second.title}
- claim: {second.claim}

Reviews:
{review_lines}

Return only valid JSON with:
winner ("first", "second", or "tie"), rationale, judge_trace, uncertainty, debate_transcript, outcome.
{_feedback_block(agent_feedback)}"""


def _multi_round_debate_round_prompt(
    goal: ResearchGoal,
    first: Hypothesis,
    second: Hypothesis,
    reviews: list[Review],
    round_index: int,
    rounds: int,
    transcript: list[str],
) -> str:
    review_lines = "\n".join(
        f"- {review.id} for {review.hypothesis_id}: {review.decision}; "
        f"strengths={'; '.join(review.strengths)}; weaknesses={'; '.join(review.weaknesses)}"
        for review in reviews
    ) or "- No reviews available."
    transcript_text = "\n".join(f"- {line}" for line in transcript) or "- No prior debate rounds."
    round_role = "opening argument" if round_index == 1 else "rebuttal and refinement"
    return f"""You are running multi-round debate round {round_index} of {rounds} for a coding-agent AI co-scientist.
Objective: {goal.objective}
{_goal_guidance_block(goal)}
Round role: {round_role}

First candidate:
- id: {first.id}
- title: {first.title}
- claim: {first.claim}

Second candidate:
- id: {second.id}
- title: {second.title}
- claim: {second.claim}

Reviews:
{review_lines}

Prior transcript:
{transcript_text}

Return only valid JSON with a debate_transcript array containing concise lines for this round.
"""


def _multi_round_debate_judge_prompt(
    goal: ResearchGoal,
    first: Hypothesis,
    second: Hypothesis,
    reviews: list[Review],
    transcript: list[str],
    rounds: int,
    agent_feedback: list[str] | None = None,
) -> str:
    review_lines = "\n".join(
        f"- {review.id} for {review.hypothesis_id}: {review.decision}; "
        f"strengths={'; '.join(review.strengths)}; weaknesses={'; '.join(review.weaknesses)}"
        for review in reviews
    ) or "- No reviews available."
    transcript_text = "\n".join(f"- {line}" for line in transcript) or "- No debate transcript available."
    return f"""You are the multi-round debate final judge for a coding-agent AI co-scientist.
Objective: {goal.objective}
{_goal_guidance_block(goal)}
Completed rounds: {rounds}

First candidate:
- id: {first.id}
- title: {first.title}
- claim: {first.claim}

Second candidate:
- id: {second.id}
- title: {second.title}
- claim: {second.claim}

Reviews:
{review_lines}

Debate transcript:
{transcript_text}

Return only valid JSON with:
winner ("first", "second", or "tie"), rationale, judge_trace, uncertainty, debate_transcript, outcome.
{_feedback_block(agent_feedback)}"""


def _proximity_prompt(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    evidence_store: EvidenceStore | None,
) -> str:
    hypothesis_lines = "\n".join(
        f"- {item.id}: title={item.title}; claim={item.claim}; evidence_refs={', '.join(item.evidence_refs) or 'none'}"
        for item in hypotheses
    ) or "- No hypotheses."
    review_lines = "\n".join(
        f"- {review.id} for {review.hypothesis_id}: {review.review_type}; "
        f"decision={review.decision}; findings={'; '.join(review.findings)}; "
        f"evidence_refs={', '.join(review.evidence_refs) or 'none'}"
        for review in reviews[-16:]
    ) or "- No reviews."
    evidence = evidence_store.evidence[:8] if evidence_store else []
    return f"""You are a goal-aware proximity agent for a coding-agent AI co-scientist.
Group related hypotheses for clustering, deduplication, and follow-up scheduling.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Hypotheses:
{hypothesis_lines}

Reviews:
{review_lines}

Evidence:
{_evidence_prompt_lines(evidence)}

Return only valid JSON with an edges array. Each edge needs:
source, target, similarity, reason, cluster_id, evidence_refs, review_refs.
Only use source and target ids from the hypothesis list.
"""


def _llm_proximity_neighborhood_prompt(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    evidence_store: EvidenceStore | None,
) -> str:
    return f"""Proximity turn 1 semantic neighborhood mapping for a coding-agent AI co-scientist worker.
Map candidate neighborhoods for clustering, deduplication, and exploration.
Objective: {goal.objective}

Hypotheses:
{_proximity_hypothesis_lines(hypotheses)}

Reviews:
{_proximity_review_lines(reviews)}

Evidence:
{_evidence_prompt_lines(evidence_store.evidence[:8] if evidence_store else [])}

Describe likely semantic neighborhoods and outliers. Do not finalize JSON yet."""


def _llm_proximity_overlap_prompt(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    evidence_store: EvidenceStore | None,
    neighborhood_text: str,
) -> str:
    return f"""Proximity turn 2 evidence and review overlap for a coding-agent AI co-scientist worker.
Objective: {goal.objective}

Turn 1 semantic neighborhood map:
{_truncate(neighborhood_text, 2200)}

Hypotheses:
{_proximity_hypothesis_lines(hypotheses)}

Reviews:
{_proximity_review_lines(reviews)}

Evidence:
{_evidence_prompt_lines(evidence_store.evidence[:8] if evidence_store else [])}

Analyze shared evidence refs, review refs, contradictions, diversity gaps, and deduplication signals. Do not finalize JSON yet."""


def _llm_proximity_synthesis_prompt(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    reviews: list[Review],
    evidence_store: EvidenceStore | None,
    neighborhood_text: str,
    overlap_text: str,
    agent_feedback: list[str] | None = None,
) -> str:
    return f"""Proximity turn 3 clustering synthesis for a coding-agent AI co-scientist worker.
Objective: {goal.objective}

Turn 1 semantic neighborhood map:
{_truncate(neighborhood_text, 1400)}

Turn 2 evidence/review overlap:
{_truncate(overlap_text, 1800)}

Hypotheses:
{_proximity_hypothesis_lines(hypotheses)}

Reviews:
{_proximity_review_lines(reviews)}

Evidence:
{_evidence_prompt_lines(evidence_store.evidence[:8] if evidence_store else [])}

Return only valid JSON with an edges array. Each edge needs:
source, target, similarity, reason, cluster_id, evidence_refs, review_refs.
Prefer also including deduplication_action and diversity_action when the pair
should be merged, contrasted, deprioritized as redundant, or preserved for diversity.
Only use source and target ids from the hypothesis list.{_feedback_block(agent_feedback)}"""


def _proximity_hypothesis_lines(hypotheses: list[Hypothesis]) -> str:
    return "\n".join(
        f"- {item.id}: title={item.title}; claim={item.claim}; evidence_refs={', '.join(item.evidence_refs) or 'none'}"
        for item in hypotheses
    ) or "- No hypotheses."


def _proximity_review_lines(reviews: list[Review]) -> str:
    return "\n".join(
        f"- {review.id} for {review.hypothesis_id}: {review.review_type}; "
        f"decision={review.decision}; findings={'; '.join(review.findings)}; "
        f"evidence_refs={', '.join(review.evidence_refs) or 'none'}"
        for review in reviews[-16:]
    ) or "- No reviews."


def _proximity_embedding_query(hypothesis: Hypothesis) -> str:
    return " ".join([hypothesis.title, hypothesis.claim])


def _proximity_control_actions(similarity: float, evidence_refs: list[str]) -> tuple[str, str]:
    if similarity >= 0.78 or (similarity >= 0.68 and evidence_refs):
        return (
            "merge_or_contrast_before_ranking",
            "avoid_redundant_parallel_exploration",
        )
    if similarity <= 0.35:
        return ("", "preserve_as_diversity_candidate")
    return ("", "schedule_for_cluster_coverage")


def _evolution_prompt(
    goal: ResearchGoal,
    parents: list[Hypothesis],
    feedback: list[str],
    evidence: list[Any],
    limit: int,
) -> str:
    parent_lines = "\n".join(
        f"- {parent.id}: {parent.title}; claim={parent.claim}; risks={'; '.join(parent.risks)}"
        for parent in parents
    ) or "- No parents supplied."
    feedback_text = "\n".join(f"- {item}" for item in feedback) or "- Tighten evidence and feasibility."
    return f"""You are an evolution agent for a coding-agent AI co-scientist.
Create up to {limit} evolved hypotheses.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Parents:
{parent_lines}

Feedback:
{feedback_text}

Evidence:
{_evidence_prompt_lines(evidence)}

Return only valid JSON with a hypotheses list. Each item needs:
title, claim, rationale, assumptions, risks, evidence_refs.
"""


def _meta_review_prompt(
    goal: ResearchGoal,
    reviews: list[Review],
    matches: list[Match],
    evidence: list[Any],
) -> str:
    review_lines = "\n".join(
        f"- {review.id} {review.review_type} {review.hypothesis_id}: {review.decision}; "
        f"weaknesses={'; '.join(review.weaknesses)}"
        for review in reviews[-12:]
    ) or "- No reviews."
    match_lines = "\n".join(
        f"- {match.id}: {match.hypothesis_a} vs {match.hypothesis_b}; winner={match.winner}; "
        f"uncertainty={match.uncertainty}"
        for match in matches[-8:]
    ) or "- No matches."
    return f"""You are a meta-review agent for a coding-agent AI co-scientist.
Objective: {goal.objective}
{_goal_guidance_block(goal)}

Recent reviews:
{review_lines}

Recent matches:
{match_lines}

Evidence:
{_evidence_prompt_lines(evidence)}

Return only valid JSON with:
common_weaknesses, safety_concerns, missing_evidence, promising_directions, prompt_feedback,
agent_feedback, evidence_refs.
"""


def _overview_prompt(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    meta_reviews: list[MetaReview],
    cycle: int,
) -> str:
    leaders = sorted(hypotheses, key=lambda item: item.elo, reverse=True)[:5]
    leader_lines = "\n".join(
        f"- {item.id}: {item.title}; elo={item.elo:.1f}; claim={item.claim}"
        for item in leaders
    ) or "- No leaders."
    latest_meta = meta_reviews[-1] if meta_reviews else None
    meta_text = (
        f"Promising directions: {'; '.join(latest_meta.promising_directions)}. "
        f"Missing evidence: {'; '.join(latest_meta.missing_evidence)}."
        if latest_meta
        else "No meta-review yet."
    )
    return f"""Create a research overview for the coding-agent AI co-scientist.
Objective: {goal.objective}
{_goal_guidance_block(goal)}
Cycle: {cycle}

Leaders:
{leader_lines}

Meta-review context:
{meta_text}

Return only valid JSON with:
summary, top_hypothesis_ids, promising_directions, next_experiments, limitations.
"""


def _evidence_prompt_lines(evidence: list[Any]) -> str:
    if not evidence:
        return "- No evidence available."
    return "\n".join(
        f"- {getattr(item, 'id', 'evidence')}: {getattr(item, 'content', '')} "
        f"source={getattr(item, 'source', '')}"
        for item in evidence[:8]
    )


def _semantic_terms(hypothesis: Hypothesis, reviews: list[Review]) -> set[str]:
    text_parts = [
        hypothesis.title,
        hypothesis.claim,
        hypothesis.rationale,
        " ".join(hypothesis.assumptions),
        " ".join(hypothesis.risks),
    ]
    for review in reviews:
        text_parts.extend(
            [
                " ".join(review.strengths),
                " ".join(review.weaknesses),
                " ".join(review.findings),
            ]
        )
    return {token for token in _tokens(" ".join(text_parts)) if token not in _STOPWORDS}


def _debate_score(hypothesis: Hypothesis, reviews: list[Review]) -> float:
    score = float(_rank_score(hypothesis))
    score += len(hypothesis.evidence_refs) * 0.75
    for review in reviews:
        score += sum(review.scores.values()) / 10 if review.scores else 0.0
        score += len(review.strengths) * 0.5
        score -= len(review.weaknesses) * 0.5
        score += len(review.evidence_refs) * 0.5
        if review.decision == "accept":
            score += 1.0
        if review.decision == "revise" or review.requires_revision:
            score -= 1.5
    score += _manual_review_signal(reviews)
    return round(score, 3)


def _manual_review_signal(reviews: list[Review]) -> float:
    signal = 0.0
    for review in reviews:
        if review.review_type != "manual_review":
            continue
        if review.decision == "accept" and not review.requires_revision:
            signal += 0.75
        if review.decision in {"revise", "reject"} or review.requires_revision:
            signal -= 0.75
    return signal


def _retrieve_pair_debate_evidence(
    evidence_store: EvidenceStore | None,
    first: Hypothesis,
    second: Hypothesis,
) -> tuple[list[str], list[str]]:
    if evidence_store is None:
        return [], []
    bundle = evidence_store.retrieve(
        " ".join(
            [
                first.title,
                first.claim,
                second.title,
                second.claim,
                "pairwise debate benchmark evidence comparison",
            ]
        ),
        limit=3,
    )
    lines = [
        f"Retrieved debate evidence {item.id} from {item.source}: {item.content}"
        for item in bundle.evidence
    ]
    return bundle.evidence_refs, lines


_STOPWORDS = {
    "and",
    "the",
    "that",
    "with",
    "will",
    "from",
    "into",
    "than",
    "before",
    "after",
    "this",
    "should",
    "agent",
    "agents",
    "coding",
    "hypothesis",
}


def _assumption_decomposition_hypotheses(
    goal: ResearchGoal,
    evidence: list[Any],
    limit: int,
) -> list[Hypothesis]:
    evidence_refs = [getattr(item, "id", "") for item in evidence][:3]
    blueprints = [
        (
            "Assumption audit before repo mutation",
            "A pre-edit assumption audit that names call-path, invariant, and test-scope assumptions will reduce bad coding-agent patches.",
            [
                "The agent can enumerate concrete assumptions before editing.",
                "A reviewer can cheaply reject false assumptions before patching.",
            ],
            ["extra review latency", "assumption lists may become boilerplate"],
        ),
        (
            "Assumption freshness checks for memory",
            "A memory check that marks stale assumptions before planning will reduce repeated long-horizon coding-agent errors.",
            [
                "Stored observations can be dated and scoped to a repository state.",
                "Contradictory fresh evidence can override stale memory.",
            ],
            ["over-filtering useful memory", "missed stale facts"],
        ),
    ]
    hypotheses: list[Hypothesis] = []
    for title, claim, assumptions, risks in blueprints[:limit]:
        hypotheses.append(
            Hypothesis(
                id=stable_id("hyp", f"{goal.id}:assumption_decomposition:{title}:{claim}"),
                title=title,
                claim=claim,
                rationale=(
                    "Assumption decomposition translates the paper's decomposition/debate behavior "
                    "into an auditable coding-agent workflow."
                ),
                assumptions=assumptions,
                evidence_refs=[ref for ref in evidence_refs if ref],
                test_plan=TestPlan(
                    experiment=f"Run a repo-repair benchmark with and without: {title}.",
                    metrics=goal.metrics,
                    success_condition="Candidate reduces regressions without unacceptable wall-time or cost increase.",
                ),
                risks=risks,
                origin="generation:assumption_decomposition",
                generation_trace=_generation_trace(
                    goal,
                    title,
                    [ref for ref in evidence_refs if ref],
                    len(assumptions),
                    "generation:assumption_decomposition",
                ),
            )
        )
    return hypotheses


def _simulated_debate_hypotheses(
    goal: ResearchGoal,
    candidates: list[Hypothesis],
    mode: str,
) -> list[Hypothesis]:
    debated: list[Hypothesis] = []
    for index, candidate in enumerate(candidates, start=1):
        evidence_refs = _unique_refs(candidate.evidence_refs)
        debate_trace = [
            f"Round 1 Pro {index}: {candidate.claim}",
            (
                f"Round 2 Critique {index}: risks={', '.join(candidate.risks) or 'none'}; "
                f"evidence refs={', '.join(evidence_refs) or 'none'}."
            ),
            (
                f"Round 3 Rebuttal {index}: assumptions={len(candidate.assumptions)}; "
                f"test plan={candidate.test_plan.experiment}"
            ),
            (
                f"Round 4 Synthesis {index}: preserve {candidate.title} only if "
                f"{', '.join(candidate.test_plan.metrics) or 'target metrics'} improve under benchmark evidence."
            ),
            (
                "Debate generation assessment: "
                f"mode={mode}; evidence refs={len(evidence_refs)}; "
                f"risks={len(candidate.risks)}; testable={bool(candidate.test_plan.experiment)}."
            ),
        ]
        debated.append(
            replace(
                candidate,
                id=stable_id("hyp", f"{goal.id}:{mode}:{candidate.id}:{candidate.claim}"),
                rationale=(
                    f"{candidate.rationale} Simulated debate retained this proposal after pro, "
                    "critique, rebuttal, and synthesis turns."
                ),
                assumptions=_unique_refs(
                    [
                        *candidate.assumptions,
                        "A simulated critique can expose weak assumptions before ranking.",
                    ]
                ),
                risks=_unique_refs(
                    [
                        *candidate.risks,
                        "simulated debate trace may overweight deterministic judge heuristics",
                    ]
                ),
                origin=f"generation:{mode}",
                generation_trace=[*candidate.generation_trace, *debate_trace],
            )
        )
    return debated


def _tool_augmented_hypotheses(
    goal: ResearchGoal,
    evidence_store: EvidenceStore,
    limit: int,
) -> list[Hypothesis]:
    selected = _select_tool_generation_evidence(goal, evidence_store, limit)
    hypotheses: list[Hypothesis] = []
    for index, item in enumerate(selected[:limit], start=1):
        tool_name = str(item.metadata.get("tool") or item.kind or "retrieval_tool")
        query = str(item.metadata.get("query") or goal.objective)
        title = f"Tool-grounded {_title_from_evidence(item.content)}"
        evidence_refs = [item.id]
        content_preview = _truncate(item.content, 220)
        hypotheses.append(
            Hypothesis(
                id=stable_id("hyp", f"{goal.id}:tool_augmented_generation:{item.id}:{item.content}"),
                title=title,
                claim=(
                    f"A workflow synthesized from {tool_name} evidence can improve "
                    f"{goal.domain} reliability for {goal.objective}."
                ),
                rationale=(
                    f"Tool-augmented generation used {tool_name} evidence {item.id} "
                    f"from {item.source}: {content_preview}"
                ),
                assumptions=[
                    "The cited tool evidence is relevant to the current research objective.",
                    "The tool observation can be converted into a measurable workflow change.",
                ],
                evidence_refs=evidence_refs,
                test_plan=TestPlan(
                    experiment=f"Implement a small workflow probe derived from {tool_name} evidence {item.id}.",
                    metrics=goal.metrics,
                    success_condition="Candidate improves pass rate or regression count without unacceptable cost increase.",
                ),
                risks=[
                    "tool evidence may be noisy, stale, or source-specific",
                    "deterministic synthesis may overfit a single tool observation",
                ],
                origin="generation:tool_augmented_generation",
                generation_trace=[
                    *_generation_trace(
                        goal,
                        title,
                        evidence_refs,
                        2,
                        "generation:tool_augmented_generation",
                    ),
                    f"Tool turn 1 query {index}: {tool_name} query `{query}`",
                    f"Tool turn 2 observation {index}: {item.id} from {item.source}: {content_preview}",
                    f"Tool turn 3 proposal synthesis {index}: {title}",
                    (
                        "Tool generation assessment: "
                        f"tool={tool_name}; evidence refs=1; testable={bool(goal.metrics)}."
                    ),
                ],
            )
        )
    return hypotheses


def _grounded_mode_hypotheses(
    goal: ResearchGoal,
    evidence_store: EvidenceStore,
    limit: int,
) -> list[Hypothesis]:
    bundle = evidence_store.retrieve(goal.objective, limit=max(limit, 1))
    selected = bundle.evidence[:limit]
    if not selected:
        return []
    hypotheses: list[Hypothesis] = []
    for item in selected:
        title = _title_from_evidence(item.content)
        hypotheses.append(
            Hypothesis(
                id=stable_id("hyp", f"{goal.id}:literature_grounded:{item.id}:{item.content}"),
                title=title,
                claim=(
                    f"A workflow derived from retrieved evidence in {item.source} can improve "
                    "LLM coding-agent reliability."
                ),
                rationale=(
                    f"Literature-grounded generation used retrieved evidence {item.id}: {item.content}"
                ),
                assumptions=[
                    "The retrieved source is relevant to the current coding-agent objective.",
                    "The source can be converted into a measurable workflow change.",
                ],
                evidence_refs=[item.id],
                test_plan=TestPlan(
                    experiment=f"Implement a small workflow probe derived from {item.source}.",
                    metrics=goal.metrics,
                    success_condition="Candidate improves pass rate or regression count without unacceptable cost increase.",
                ),
                risks=["retrieved evidence may be stale or overfit to one corpus"],
                origin="generation:literature_grounded_generation",
                generation_trace=[
                    *_generation_trace(
                        goal,
                        title,
                        [item.id],
                        2,
                        "generation:literature_grounded_generation",
                    ),
                    f"Grounded retrieval query: {goal.objective}",
                    f"Grounded retrieval evidence: {item.id}",
                ],
            )
        )
    return hypotheses


def _generation_trace(
    goal: ResearchGoal,
    title: str,
    evidence_refs: list[str],
    assumption_count: int,
    origin: str,
) -> list[str]:
    return [
        f"Turn 1 objective framing: {goal.objective}",
        f"Turn 2 evidence scan: {', '.join(evidence_refs) or 'none'}",
        f"Turn 3 proposal synthesis: {title}",
        (
            f"Generation assessment: origin={origin}; "
            f"evidence refs={len([ref for ref in evidence_refs if ref])}; assumptions={assumption_count}."
        ),
    ]


def _append_llm_generation_turn_trace(
    hypotheses: list[Hypothesis],
    mode: str,
    turns: list[str],
) -> list[Hypothesis]:
    traced: list[Hypothesis] = []
    for hypothesis in hypotheses:
        traced.append(
            replace(
                hypothesis,
                generation_trace=[
                    *hypothesis.generation_trace,
                    *turns,
                    (
                        "LLM multi-turn generation assessment: "
                        f"mode={mode}; origin={hypothesis.origin}; "
                        f"evidence refs={len(hypothesis.evidence_refs)}; "
                        f"testable={bool(hypothesis.test_plan.experiment)}."
                    ),
                ],
            )
        )
    return traced


def _select_tool_generation_evidence(
    goal: ResearchGoal,
    evidence_store: EvidenceStore,
    limit: int,
) -> list[Evidence]:
    tool_evidence = [item for item in evidence_store.evidence if _is_tool_evidence(item)]
    ranked_ids = {
        item.id
        for item in evidence_store.retrieve(goal.objective, limit=max(limit, len(tool_evidence))).evidence
        if _is_tool_evidence(item)
    }
    selected = [item for item in tool_evidence if item.id in ranked_ids] or tool_evidence
    return selected[:limit]


def _tool_proximity_evidence_refs(
    goal: ResearchGoal,
    left: Hypothesis,
    right: Hypothesis,
    evidence_store: EvidenceStore,
    limit: int = 2,
) -> list[str]:
    tool_evidence = [item for item in evidence_store.evidence if _is_tool_evidence(item)]
    if not tool_evidence:
        return []
    pair_query = " ".join(
        [
            goal.objective,
            _proximity_embedding_query(left),
            _proximity_embedding_query(right),
        ]
    )
    ranked_tools = [
        item
        for item in evidence_store.retrieve(pair_query, limit=max(len(tool_evidence), limit)).evidence
        if _is_tool_evidence(item)
    ] or tool_evidence
    left_terms = set(_tokens(_proximity_embedding_query(left)))
    right_terms = set(_tokens(_proximity_embedding_query(right)))
    selected: list[str] = []
    for item in ranked_tools:
        metadata_text = " ".join(str(value) for value in item.metadata.values())
        evidence_terms = set(_tokens(" ".join([item.content, item.notes, item.source, metadata_text])))
        if left_terms & evidence_terms and right_terms & evidence_terms:
            selected.append(item.id)
        if len(selected) >= limit:
            break
    return _unique_refs(selected)


def _llm_debate_proposal_prompt(
    goal: ResearchGoal,
    evidence: list[Any],
    mode: str,
    limit: int,
) -> str:
    return f"""Generation turn 1 debate proposal for a coding-agent AI co-scientist worker.
Mode: {mode}
Objective: {goal.objective}

Evidence:
{_evidence_prompt_text(evidence)}

Propose raw candidate directions for later critique. Do not finalize JSON yet.
Target candidate count: {limit}."""


def _llm_debate_critique_prompt(
    goal: ResearchGoal,
    evidence: list[Any],
    mode: str,
    proposal_text: str,
) -> str:
    return f"""Generation turn 2 debate critique for a coding-agent AI co-scientist worker.
Mode: {mode}
Objective: {goal.objective}

Evidence:
{_evidence_prompt_text(evidence)}

Candidate proposal from turn 1:
{_truncate(proposal_text, 3000)}

Critique assumptions, missing evidence, safety issues, and benchmark testability. Do not finalize JSON yet."""


def _llm_debate_synthesis_prompt(
    goal: ResearchGoal,
    evidence: list[Any],
    mode: str,
    proposal_text: str,
    critique_text: str,
    limit: int,
    agent_feedback: list[str] | None = None,
) -> str:
    return f"""Generation turn 3 debate synthesis for a coding-agent AI co-scientist worker.
Mode: {mode}
Objective: {goal.objective}

Evidence:
{_evidence_prompt_text(evidence)}

Turn 1 proposal:
{_truncate(proposal_text, 1800)}

Turn 2 critique:
{_truncate(critique_text, 1800)}

Return only valid JSON with this shape:
{{
  "hypotheses": [
    {{
      "title": "short title",
      "claim": "testable claim about improving LLM coding agents",
      "rationale": "why this survived proposal and critique turns",
      "assumptions": ["explicit assumption"],
      "risks": ["risk or failure mode"]
    }}
  ]
}}

Include at most {limit} hypotheses. Do not claim improvement as proven.{_feedback_block(agent_feedback)}"""


def _llm_tool_query_plan_prompt(
    goal: ResearchGoal,
    evidence: list[Evidence],
    limit: int,
) -> str:
    return f"""Generation turn 1 tool query plan for a coding-agent AI co-scientist worker.
Objective: {goal.objective}

Available tool evidence:
{_evidence_prompt_text(evidence)}

State which tool observations should drive hypothesis generation and why. Do not finalize JSON yet.
Target candidate count: {limit}."""


def _llm_tool_observation_prompt(
    goal: ResearchGoal,
    evidence: list[Evidence],
    query_plan_text: str,
) -> str:
    return f"""Generation turn 2 tool observation analysis for a coding-agent AI co-scientist worker.
Objective: {goal.objective}

Tool query plan from turn 1:
{_truncate(query_plan_text, 1800)}

Tool observations:
{_evidence_prompt_text(evidence)}

Analyze what the tool observations support, what they do not support, and which benchmark checks are needed. Do not finalize JSON yet."""


def _llm_tool_synthesis_prompt(
    goal: ResearchGoal,
    evidence: list[Evidence],
    query_plan_text: str,
    observation_text: str,
    limit: int,
    agent_feedback: list[str] | None = None,
) -> str:
    return f"""Generation turn 3 tool synthesis for a coding-agent AI co-scientist worker.
Objective: {goal.objective}

Tool query plan:
{_truncate(query_plan_text, 1400)}

Tool observation analysis:
{_truncate(observation_text, 1800)}

Tool evidence:
{_evidence_prompt_text(evidence)}

Return only valid JSON with this shape:
{{
  "hypotheses": [
    {{
      "title": "short title",
      "claim": "testable claim about improving LLM coding agents",
      "rationale": "why the tool observation supports this experimentable hypothesis",
      "assumptions": ["explicit assumption"],
      "risks": ["risk or failure mode"]
    }}
  ]
}}

Include at most {limit} hypotheses. Do not claim improvement as proven.{_feedback_block(agent_feedback)}"""


def _evidence_prompt_text(evidence: list[Any], limit: int = 5) -> str:
    lines = []
    for item in evidence[:limit]:
        lines.append(
            f"- {getattr(item, 'id', 'evidence')}: {getattr(item, 'content', '')} "
            f"Notes: {getattr(item, 'notes', '')}"
        )
    return "\n".join(lines) if lines else "- No evidence available."


def _title_from_evidence(content: str) -> str:
    words = [word.strip(".,:;()[]{}'\"") for word in content.split() if word.strip(".,:;()[]{}'\"")]
    title = " ".join(words[:6]) if words else "Retrieved evidence hypothesis"
    return title[:1].upper() + title[1:]


def _is_tool_evidence(item: Evidence) -> bool:
    kind = item.kind.lower()
    return bool(item.metadata.get("tool")) or kind.startswith("tool_result") or "search_result" in kind


def _unique_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref and ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique


def _contact_targets_for_output(
    goal: ResearchGoal,
    hypothesis: Hypothesis,
    evidence_refs: list[str],
) -> list[str]:
    targets = [
        f"Benchmark owner or maintainer for {', '.join(hypothesis.test_plan.metrics) or 'the target metrics'}",
        f"Practitioner reviewer for {goal.domain} workflows",
        f"Repository maintainer for implementing {hypothesis.title}",
    ]
    if evidence_refs:
        targets.append("Owner of cited evidence or benchmark artifacts")
    return _unique_refs(targets)


def _meaningful_terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-z]{5,}", text.lower()) if term not in _STOPWORDS}


def _recurring_weakness_terms(prior_reviews: list[Review], hypothesis_id: str) -> set[str]:
    counts: Counter[str] = Counter()
    for review in prior_reviews:
        if review.hypothesis_id != hypothesis_id:
            continue
        for weakness in review.weaknesses:
            counts.update(_meaningful_terms(weakness))
    return {term for term, count in counts.items() if count >= 2}


def _looks_contradictory(text: str) -> bool:
    lowered = text.lower()
    contradiction_markers = (
        "contradict",
        "failed to improve",
        "did not improve",
        "does not improve",
        "no improvement",
        "reduced pass_rate",
        "lower pass_rate",
        "increased regression",
        "more regressions",
        "worse",
    )
    return any(marker in lowered for marker in contradiction_markers)


def _verify_explicit_assumptions(
    hypothesis: Hypothesis,
    evidence_store: EvidenceStore | None,
) -> list[AssumptionCheck]:
    """Deterministic fallback for the paper's assumption-level verification pass.

    The provider-backed worker can emit a deeper parent/child tree. The fallback is
    intentionally conservative: it independently checks only assumptions explicitly
    stated by the hypothesis and leaves unsupported ones uncertain.
    """
    checks: list[AssumptionCheck] = []
    for index, assumption in enumerate(hypothesis.assumptions):
        query = " ".join([hypothesis.title, hypothesis.claim, assumption, "evidence contradiction validation"])
        retrieved = evidence_store.retrieve(query, limit=5).evidence if evidence_store else []
        assumption_terms = _meaningful_terms(assumption)
        relevant = [
            item
            for item in retrieved
            if len(assumption_terms & _meaningful_terms(" ".join([item.content, item.notes]))) >= 2
        ]
        contradictions = [item for item in relevant if _looks_contradictory(item.content)]
        if contradictions:
            verdict = "contradicted"
            selected = contradictions
            reasoning = "Retrieved evidence directly reports failure or contradiction of this assumption."
        elif relevant:
            verdict = "supported"
            selected = relevant
            reasoning = "Retrieved evidence contains relevant support and no explicit contradiction marker."
        else:
            verdict = "uncertain"
            selected = []
            reasoning = "No sufficiently relevant evidence was retrieved for an independent verdict."
        fundamental = _is_fundamental_assumption(assumption)
        invalidates = verdict == "contradicted" and fundamental
        checks.append(
            AssumptionCheck(
                id=stable_id("assumption-check", f"{hypothesis.id}:{index}:{assumption}:{verdict}"),
                assumption=assumption,
                parent_assumption="",
                depth=0,
                verdict=verdict,
                fundamental=fundamental,
                invalidates_hypothesis=invalidates,
                evidence_refs=[item.id for item in selected],
                reasoning=reasoning,
            )
        )
    return checks


def _is_fundamental_assumption(assumption: str) -> bool:
    lowered = assumption.lower()
    repairable_markers = (
        "optional",
        "secondary",
        "implementation detail",
        "nice to have",
        "optimization",
        "optimisation",
    )
    return not any(marker in lowered for marker in repairable_markers)


def _assumption_checks_from_llm_payload(
    response_text: str,
    hypothesis: Hypothesis,
    default_evidence_refs: list[str],
) -> list[AssumptionCheck]:
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    return _assumption_checks_from_data(
        data.get("assumption_checks"),
        hypothesis=hypothesis,
        default_evidence_refs=default_evidence_refs,
    )


def _assumption_checks_from_data(
    value: Any,
    hypothesis: Hypothesis,
    default_evidence_refs: list[str],
) -> list[AssumptionCheck]:
    if not isinstance(value, list):
        return []
    checks: list[AssumptionCheck] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        assumption = _clean_string(raw.get("assumption"), "")
        if not assumption:
            continue
        verdict = _clean_string(raw.get("verdict"), "uncertain").lower()
        if verdict not in {"supported", "contradicted", "uncertain"}:
            verdict = "uncertain"
        parent_assumption = _clean_string(raw.get("parent_assumption"), "")
        try:
            depth = max(int(raw.get("depth", 1 if parent_assumption else 0)), 0)
        except (TypeError, ValueError):
            depth = 1 if parent_assumption else 0
        fundamental = _bool_value(raw.get("fundamental"), _is_fundamental_assumption(assumption))
        invalidates = verdict == "contradicted" and fundamental
        checks.append(
            AssumptionCheck(
                id=stable_id("assumption-check", f"{hypothesis.id}:llm:{index}:{assumption}:{verdict}"),
                assumption=assumption,
                parent_assumption=parent_assumption,
                depth=depth,
                verdict=verdict,
                fundamental=fundamental,
                invalidates_hypothesis=invalidates,
                evidence_refs=_string_list(raw.get("evidence_refs"), default_evidence_refs),
                reasoning=_clean_string(
                    raw.get("reasoning"),
                    "The provider returned no assumption-level reasoning.",
                ),
            )
        )
    return checks


def _merge_assumption_checks(
    earlier: list[AssumptionCheck],
    later: list[AssumptionCheck],
) -> list[AssumptionCheck]:
    """Merge turn-level checks without letting synthesis silently erase a failure."""
    merged: dict[tuple[str, str, int], AssumptionCheck] = {
        (item.assumption, item.parent_assumption, item.depth): item for item in earlier
    }
    for item in later:
        key = (item.assumption, item.parent_assumption, item.depth)
        previous = merged.get(key)
        if previous and previous.verdict == "contradicted" and item.verdict != "contradicted":
            continue
        merged[key] = item
    return list(merged.values())


def _bool_value(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _looks_like_prior_art(text: str) -> bool:
    lowered = text.lower()
    markers = ("known baseline", "common prior art", "prior art", "already known", "well-known", "standard")
    return any(marker in lowered for marker in markers)


def _looks_like_observation_evidence(item: Evidence) -> bool:
    lowered = " ".join([item.kind, item.content, item.notes, item.source]).lower()
    markers = (
        "runtime observation",
        "observation",
        "failure trace",
        "repair trace",
        "trace",
        "repository",
        "repo",
        "log",
        "tool_result",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_simulation_evidence(item: Evidence) -> bool:
    lowered = " ".join([item.kind, item.content, item.notes, item.source]).lower()
    markers = (
        "simulation",
        "simulated",
        "benchmark",
        "pass_rate",
        "regression_count",
        "candidate_metrics",
        "baseline_metrics",
        "prospective",
        "scaling",
    )
    return any(marker in lowered for marker in markers)


def _compare_observation_to_hypothesis(
    hypothesis: Hypothesis,
    item: Evidence,
    index: int,
    *,
    simulation: bool = False,
) -> tuple[str, str, list[str]]:
    text = " ".join([item.content, item.notes]).lower()
    contradiction_markers = (
        "did not improve",
        "no improvement",
        "candidate failed",
        "hypothesis failed",
        "experiment failed",
        "test failed",
        "failed to",
        "regression_count increased",
        "more regressions",
        "worse",
        "pass_rate decreased",
        "pass rate decreased",
        "contradict",
    )
    support_markers = (
        "improved",
        "increase",
        "higher",
        "passed",
        "success",
        "caught",
        "catch",
        "reduced",
    )
    if any(marker in text for marker in contradiction_markers):
        verdict = "contradicts"
        reason = "the measured or observed outcome contains an explicit failure/regression signal"
    elif any(marker in text for marker in support_markers):
        verdict = "supports"
        reason = "the outcome contains a positive mechanism or metric signal"
    else:
        verdict = "inconclusive"
        reason = "the record lacks an explicit directional result tied to the success condition"
    label = "Simulation outcome" if simulation else "Observation"
    explanation = (
        f"{label} {index} ({item.id}) {verdict} the hypothesis: {reason}."
    )
    trace_prefix = "Simulation step 3" if simulation else f"Observation {index}"
    trace_lines = [
        f"{trace_prefix} - prediction: {hypothesis.claim}",
        f"{trace_prefix} - observed: {_truncate(item.content, 240)}",
        f"{trace_prefix} - comparison: {verdict}; {reason}.",
    ]
    return verdict, explanation, trace_lines


def _review_evidence_matching(
    evidence_store: EvidenceStore | None,
    query: str,
    predicate: Callable[[Evidence], bool],
    limit: int = 5,
) -> list[Evidence]:
    if evidence_store is None:
        return []
    retrieved = evidence_store.retrieve(query, limit=max(limit, len(evidence_store.evidence))).evidence
    candidates = [item for item in retrieved if predicate(item)]
    if not candidates:
        candidates = [item for item in evidence_store.evidence if predicate(item)]
    return candidates[:limit]


def _grounded_review_from_initial(
    initial: Review,
    findings: list[str],
    evidence_refs: list[str],
    confidence: float,
    requires_revision: bool,
    decision: str,
    weaknesses: list[str],
    scores: dict[str, int] | None = None,
    review_type: str = "full_review",
    review_trace: list[str] | None = None,
    safety_notes: list[str] | None = None,
    assumption_checks: list[AssumptionCheck] | None = None,
) -> Review:
    return Review(
        id=stable_id("rev", f"{initial.id}:{review_type}:{','.join(evidence_refs)}:{decision}"),
        hypothesis_id=initial.hypothesis_id,
        decision=decision,
        scores=scores or dict(initial.scores),
        strengths=initial.strengths,
        weaknesses=weaknesses,
        safety_notes=safety_notes or initial.safety_notes,
        review_type=review_type,
        evidence_refs=evidence_refs,
        findings=findings,
        review_trace=review_trace or [],
        confidence=confidence,
        requires_revision=requires_revision,
        assumption_checks=assumption_checks or [],
    )


def _truncate(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(limit - 3, 0)].rstrip() + "..."


def _rank_score(hypothesis: Hypothesis) -> int:
    return (
        len(hypothesis.assumptions)
        + len(hypothesis.evidence_refs)
        + len(hypothesis.test_plan.metrics)
        - len([risk for risk in hypothesis.risks if "unsafe" in risk.lower()])
    )


def _expansion_context_block(
    existing_hypotheses: list[Hypothesis],
    research_overview: Any | None,
) -> str:
    if not existing_hypotheses and research_overview is None:
        return ""
    titles = "; ".join(item.title for item in existing_hypotheses) or "none"
    overview_summary = ""
    if research_overview is not None and getattr(research_overview, "summary", ""):
        overview_summary = f" Overview summary: {research_overview.summary}"
    limitations = ""
    if research_overview is not None and getattr(research_overview, "limitations", None):
        limitations = f" Overview gaps: {'; '.join(research_overview.limitations[:2])}."
    return (
        "\n\nResearch expansion context: already-explored hypotheses are: "
        f"{titles}.{overview_summary}{limitations} "
        "Target unexplored areas relative to these existing hypotheses.\n"
    )


def _generation_prompt(
    goal: ResearchGoal,
    evidence: list[Any],
    limit: int,
    agent_feedback: list[str] | None = None,
    expansion_context: str = "",
) -> str:
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
{_goal_guidance_block(goal)}

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
Do not claim an improvement as proven; describe an experimentable hypothesis.{expansion_context}{_feedback_block(agent_feedback)}"""


def _json_repair_prompt(goal: ResearchGoal, invalid_response: str, limit: int) -> str:
    return f"""Previous response was invalid JSON for this objective:
{goal.objective}

Return a compact valid JSON object only. No markdown. No commentary.
Use exactly this schema:
{{"hypotheses":[{{"title":"short title","claim":"testable claim","rationale":"why this could work","assumptions":["explicit assumption"],"risks":["risk"]}}]}}

Include at most {limit} hypotheses.
Previous invalid response:
{invalid_response[:3000]}"""


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
                generation_trace=_string_list(
                    raw_item.get("generation_trace"),
                    _generation_trace(
                        goal,
                        title,
                        evidence_refs,
                        len(_text_list(raw_item.get("assumptions"))),
                        origin,
                    ),
                ),
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
