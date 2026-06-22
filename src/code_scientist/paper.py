from __future__ import annotations

from code_scientist.models import Evidence, stable_id


def _evidence(kind: str, content: str, notes: str) -> Evidence:
    return Evidence(
        id=stable_id("ev", content),
        kind=kind,
        source="2502.18864.pdf",
        content=content,
        notes=notes,
    )


def seed_paper_evidence() -> list[Evidence]:
    return [
        _evidence(
            "paper_architecture",
            "The AI co-scientist uses a generate, debate, and evolve approach to hypothesis generation.",
            "Core loop to translate into AI/LLM improvement research.",
        ),
        _evidence(
            "paper_architecture",
            "A supervisor coordinates specialized generation, reflection, ranking, proximity, evolution, and meta-review agents.",
            "Agent decomposition for the Code Scientist MVP.",
        ),
        _evidence(
            "paper_plan_configuration",
            "The system parses a natural language research goal into a research plan configuration with preferences, constraints, and evaluation criteria.",
            "Code Scientist should persist the derived plan instead of keeping it implicit.",
        ),
        _evidence(
            "paper_evaluation",
            "The ranking agent uses an Elo-based tournament to prioritize hypotheses, while noting that Elo is an auto-evaluation proxy.",
            "Ranking should be auditable and labeled as proxy evaluation.",
        ),
        _evidence(
            "paper_proximity",
            "The proximity agent builds a graph of related hypotheses to support clustering, de-duplication, diverse exploration, and tournament scheduling.",
            "Similarity edges should be stored and used when choosing pairwise matches.",
        ),
        _evidence(
            "paper_feedback_loop",
            "Meta-review synthesizes recurring critique patterns and appends feedback to future agent prompts without model retraining.",
            "Self-improvement should start as externalized prompt and process feedback.",
        ),
        _evidence(
            "paper_context_memory",
            "The supervisor periodically writes context memory containing system state, progress statistics, and feedback for later computation.",
            "Runs need restartable progress snapshots and scheduler statistics.",
        ),
        _evidence(
            "paper_safety",
            "The system reviews research goals and generated hypotheses for safety and keeps comprehensive logs for auditability.",
            "Safety gates are required before ranking and reporting ideas.",
        ),
        _evidence(
            "paper_limitations",
            "The paper warns that literature search can miss prior work, LLMs can hallucinate, and auto-evaluation metrics need broader validation.",
            "Reports must separate generated hypotheses from verified improvements.",
        ),
    ]
