from __future__ import annotations

import json
from typing import Any

from code_scientist.llm import LLMResponseError
from code_scientist.models import ResearchGoal, ResearchPlanConfig, stable_id


def parse_research_plan_with_llm(
    goal: ResearchGoal,
    llm_client: Any,
    max_tokens: int = 1024,
) -> ResearchPlanConfig:
    response_text = llm_client.complete(_plan_prompt(goal), max_tokens=max_tokens)
    data = _loads_object(response_text, "research plan")
    default = ResearchPlanConfig.from_goal(goal)
    scheduler_weights = {
        **default.scheduler_weights,
        **_float_mapping(data.get("scheduler_weights")),
    }
    identity = f"{goal.id}:llm-plan:{json.dumps(data, sort_keys=True)}"
    return ResearchPlanConfig(
        id=stable_id("plan", identity),
        goal_id=goal.id,
        proposal_preferences=_string_list(data.get("proposal_preferences"), default.proposal_preferences),
        evaluation_criteria=_string_list(data.get("evaluation_criteria"), default.evaluation_criteria),
        generation_methods=_string_list(data.get("generation_methods"), default.generation_methods),
        review_types=_string_list(data.get("review_types"), default.review_types),
        evolution_strategies=_string_list(data.get("evolution_strategies"), default.evolution_strategies),
        scheduler_weights=scheduler_weights,
        constraints=_string_list(data.get("constraints"), default.constraints),
        output_formats=_string_list(data.get("output_formats"), default.output_formats),
        allowed_sources=_string_list(data.get("allowed_sources"), default.allowed_sources),
        allowed_tools=_string_list(data.get("allowed_tools"), default.allowed_tools),
        termination_criteria=_string_list(data.get("termination_criteria"), default.termination_criteria),
    )


def _plan_prompt(goal: ResearchGoal) -> str:
    return f"""You are configuring a coding-agent AI co-scientist research plan.
Objective:
{goal.objective}

Scientist preferences:
{_bullet_list(goal.preferences)}

Scientist constraints:
{_bullet_list(goal.constraints)}

Requested metrics:
{_bullet_list(goal.metrics)}

Safety notes:
{_bullet_list(goal.safety_notes)}

Allowed sources:
{_bullet_list(goal.allowed_sources)}

Allowed tools:
{_bullet_list(goal.allowed_tools)}

Return only valid JSON with these keys:
- proposal_preferences: string[]
- evaluation_criteria: string[]
- generation_methods: string[]
- review_types: string[]
- evolution_strategies: string[]
- scheduler_weights: object with numeric weights for generation, reflection, proximity, ranking, evolution, meta_review
- constraints: string[]
- output_formats: string[]
- allowed_sources: string[]
- allowed_tools: string[]
- termination_criteria: string[]
"""


def _bullet_list(values: list[str]) -> str:
    if not values:
        return "- none specified"
    return "\n".join(f"- {value}" for value in values)


def _loads_object(response_text: str, context: str) -> dict[str, Any]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM {context} response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMResponseError(f"LLM {context} response must be a JSON object.")
    return data


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return items or list(fallback)


def _float_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, float] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        try:
            parsed[key] = float(raw)
        except (TypeError, ValueError):
            continue
    return parsed
