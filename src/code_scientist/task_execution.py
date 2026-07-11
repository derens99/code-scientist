from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from code_scientist.agents import ReflectionAgent
from code_scientist.coordination import SQLiteTaskCoordinator, atomic_write_json
from code_scientist.evidence import EvidenceStore
from code_scientist.llm import create_llm_client, is_llm_provider
from code_scientist.models import (
    AgentTrace,
    Evidence,
    Hypothesis,
    Match,
    ResearchGoal,
    Review,
    Task,
    stable_id,
)
from code_scientist.safety import SafetyPolicy


class UnsupportedTaskPacket(ValueError):
    pass


ProviderClientFactory = Callable[[str, str, str], Any]


@dataclass(frozen=True)
class ProviderRuntime:
    provider: str = "deterministic"
    model: str = ""
    env_file: str = ".env"
    max_tokens: int = 4096
    coordinator: SQLiteTaskCoordinator | None = None
    budget_name: str = "provider_calls"


_REVIEW_TYPES = {
    "initial_review",
    "full_review",
    "safety_review",
    "recurrent_tournament_review",
    "novelty_review",
    "deep_verification",
    "observation_review",
    "simulation_review",
}


def execute_task_packet(
    task: Task,
    run_dir: str | Path,
    *,
    provider_client_factory: ProviderClientFactory | None = None,
    provider_runtime: ProviderRuntime | None = None,
) -> list[str]:
    """Execute a serializable, no-shell task packet and return durable result refs."""

    packet_type = str(task.payload.get("packet_type", "")).strip()
    if packet_type in {"deterministic_review", "provider_review"}:
        return _execute_review_packet(
            task,
            Path(run_dir),
            provider_client_factory=provider_client_factory,
            provider_runtime=provider_runtime or ProviderRuntime(),
        )
    if packet_type == "write_artifact":
        return _execute_write_artifact(task, Path(run_dir))
    raise UnsupportedTaskPacket(f"Unsupported or missing packet_type for {task.id}: {packet_type}")


def _execute_review_packet(
    task: Task,
    run_dir: Path,
    *,
    provider_client_factory: ProviderClientFactory | None,
    provider_runtime: ProviderRuntime,
) -> list[str]:
    _validate_review_packet_envelope(task)
    goal_data = task.payload.get("goal")
    hypothesis_data = task.payload.get("hypothesis")
    raw_evidence = task.payload.get("evidence", [])
    if not isinstance(goal_data, dict) or not isinstance(hypothesis_data, dict):
        raise ValueError("deterministic_review requires serialized goal and hypothesis objects")
    if not isinstance(raw_evidence, list):
        raise ValueError("review packet evidence must be a list")
    goal = ResearchGoal.from_dict(goal_data)
    hypothesis = Hypothesis.from_dict(hypothesis_data)
    evidence = [Evidence.from_dict(item) for item in raw_evidence if isinstance(item, dict)]
    raw_review_types = task.payload.get("review_types")
    review_types = list(dict.fromkeys(
        [str(item).strip() for item in raw_review_types if str(item).strip()]
        if isinstance(raw_review_types, list)
        else [str(task.payload.get("review_type", "initial_review"))]
    ))
    if not review_types or any(item not in _REVIEW_TYPES for item in review_types):
        raise ValueError("Review packet contains an unsupported review type")
    llm_client = None
    required_provider = str(task.payload.get("required_provider", "deterministic")).strip().lower()
    required_model = str(task.payload.get("required_model", "")).strip()
    requested_max_tokens = max(int(task.payload.get("requested_max_tokens", 1024)), 1)
    runtime_provider = provider_runtime.provider.strip().lower()
    runtime_model = provider_runtime.model.strip()
    if task.payload.get("packet_type") == "provider_review":
        if not is_llm_provider(required_provider) or runtime_provider != required_provider:
            raise ValueError("Provider review packet is not authorized by this worker runtime")
        if required_model and runtime_model != required_model:
            raise ValueError("Provider review packet model is not authorized by this worker runtime")
        if requested_max_tokens > max(int(provider_runtime.max_tokens), 1):
            raise ValueError("Provider review packet exceeds the worker token cap")
        factory = provider_client_factory or _provider_client_from_environment
        llm_client = factory(runtime_provider, runtime_model, provider_runtime.env_file)
        if provider_runtime.coordinator is not None:
            llm_client = _BudgetedProviderClient(
                llm_client,
                provider_runtime.coordinator,
                provider_runtime.budget_name,
            )
    elif required_provider != "deterministic" or runtime_provider != "deterministic":
        raise ValueError("Deterministic review packet/runtime provider mismatch")

    safety_policies = [
        SafetyPolicy.from_dict(item)
        for item in _dict_list(task.payload.get("safety_policies"))
    ]
    reflection = ReflectionAgent(
        llm_client=llm_client,
        llm_max_tokens=requested_max_tokens,
        safety_policies=safety_policies,
    )
    store = EvidenceStore(evidence) if bool(task.payload.get("use_grounded", False)) else None
    reflection_feedback = _string_list(task.payload.get("reflection_feedback"))
    safety_feedback = _string_list(task.payload.get("safety_feedback"))
    matches = [
        Match.from_dict(item)
        for item in _dict_list(task.payload.get("matches"))
    ]
    prior_reviews = [
        Review.from_dict(item)
        for item in _dict_list(task.payload.get("prior_reviews"))
    ]
    reviews: list[Review] = []
    for review_type in review_types:
        feedback = (
            list(dict.fromkeys([*reflection_feedback, *safety_feedback]))
            if review_type == "safety_review"
            else reflection_feedback
        )
        reviews.append(reflection.review_with_type(
            goal,
            hypothesis,
            review_type,
            store,
            agent_feedback=feedback,
            matches=matches,
            prior_reviews=prior_reviews,
        ))
    _validate_reviews(reviews, review_types, hypothesis, evidence)
    llm_interactions = reflection.consume_llm_interactions()
    output = _packet_output_path(
        run_dir,
        str(task.payload.get("output_path", f"worker-results/{task.id}.json")),
    )
    trace = AgentTrace(
        id=stable_id("trace", f"{task.id}:review-packet:{','.join(review.id for review in reviews)}"),
        cycle=int(task.payload.get("cycle", 0)),
        agent="reflection",
        action=(
            "provider_multiprocess_review_packet"
            if task.payload.get("packet_type") == "provider_review"
            else "deterministic_multiprocess_review_packet"
        ),
        task_id=task.id,
        input_refs=[goal.id, hypothesis.id, *[item.id for item in evidence]],
        output_refs=[review.id for review in reviews],
        notes=(
            f"Executed {len(reviews)} portable review(s) with provider {runtime_provider}"
            f"{f' model {runtime_model}' if runtime_model else ''}."
        ),
        evidence_refs=sorted({ref for review in reviews for ref in review.evidence_refs}),
        llm_interactions=llm_interactions,
        scratchpad=[
            f"provider={runtime_provider}",
            f"review_types={','.join(review_types)}",
            f"review_count={len(reviews)}",
        ],
        transcript_ref=f"transcripts/reflection/{task.id}.jsonl",
    )
    atomic_write_json(
        output,
        {
            "schema_version": 1,
            "packet_digest": str(task.payload.get("packet_digest", "")),
            "task_id": task.id,
            "hypothesis_id": hypothesis.id,
            "provider": runtime_provider,
            "model": runtime_model,
            "review": reviews[0].to_dict(),
            "reviews": [review.to_dict() for review in reviews],
            "agent_trace": trace.to_dict(),
        },
    )
    return [*[review.id for review in reviews], str(output)]


def _provider_client_from_environment(provider: str, model: str, env_file: str):
    if not is_llm_provider(provider):
        raise ValueError(f"Unsupported provider: {provider}")
    return create_llm_client(provider, model=model, env_file=env_file or ".env")


class _BudgetedProviderClient:
    def __init__(
        self,
        client: Any,
        coordinator: SQLiteTaskCoordinator,
        budget_name: str,
    ) -> None:
        self.client = client
        self.coordinator = coordinator
        self.budget_name = budget_name

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self.coordinator.consume_budget(self.budget_name, 1)
        return self.client.complete(prompt, max_tokens=max_tokens)


def review_packet_digest(payload: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {"packet_digest", "output_path"}
    }
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _validate_review_packet_envelope(task: Task) -> None:
    digest = str(task.payload.get("packet_digest", ""))
    if not digest or digest != review_packet_digest(task.payload):
        raise ValueError("Review packet digest is missing or invalid")


def _validate_reviews(
    reviews: list[Review],
    requested_types: list[str],
    hypothesis: Hypothesis,
    evidence: list[Evidence],
) -> None:
    if len(reviews) != len(requested_types):
        raise ValueError("Review packet returned an unexpected review count")
    allowed_refs = {item.id for item in evidence} | set(hypothesis.evidence_refs)
    for requested_type, review in zip(requested_types, reviews, strict=True):
        if review.hypothesis_id != hypothesis.id:
            raise ValueError("Review packet returned the wrong hypothesis id")
        if review.decision not in {"accept", "revise", "reject"}:
            raise ValueError("Review packet returned an invalid decision")
        acceptable_types = {requested_type, f"llm_{requested_type}"}
        if review.review_type not in acceptable_types:
            raise ValueError("Review packet returned an unexpected review type")
        if not set(review.evidence_refs).issubset(allowed_refs):
            raise ValueError("Review packet returned an evidence ref outside the packet")


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _execute_write_artifact(task: Task, run_dir: Path) -> list[str]:
    output = _packet_output_path(
        run_dir,
        str(task.payload.get("output_path", f"worker-results/{task.id}.json")),
    )
    content = task.payload.get("content", {})
    if not isinstance(content, dict):
        raise ValueError("write_artifact content must be a JSON object")
    atomic_write_json(output, {"task_id": task.id, "content": content})
    return [str(output)]


def _packet_output_path(run_dir: Path, relative_path: str) -> Path:
    root = run_dir.resolve()
    output = (root / relative_path).resolve()
    if output == root or root not in output.parents:
        raise ValueError("Task packet output_path must remain inside the run directory")
    return output
