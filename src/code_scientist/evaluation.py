from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from math import comb, sqrt
from pathlib import Path
from typing import Any

from code_scientist.models import (
    BenchmarkResult,
    CapabilityEvaluation,
    CapabilityStudyCoverage,
    CapabilityStudySummary,
    FeedbackLoopEvaluation,
    Hypothesis,
    ProspectiveEvaluation,
    ResearchGoal,
    RunState,
    ScalingCurvePoint,
    stable_id,
)


def load_capability_evaluation_fixture(
    path: str | Path,
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> CapabilityEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Capability evaluation fixture must be a JSON object: {path}")

    baseline_name = _fixture_text(data.get("baseline_name"), "single_shot_llm")
    baseline_score = _fixture_float(data.get("baseline_score"), "baseline_score")
    human_scores = _score_map(data.get("human_scores"), "human_scores")
    benchmark_scores = _score_map(data.get("benchmark_scores"), "benchmark_scores")
    human_scores.update(_scores_from_rules(hypotheses, data.get("human_score_rules")))
    benchmark_scores.update(_scores_from_rules(hypotheses, data.get("benchmark_score_rules")))
    rubric_scores, rubric_judgment_count, rubric_criteria = _scores_from_human_rubric_judgments(
        data.get("human_rubric_judgments"),
        data.get("human_rubric_scale", 5),
    )
    human_scores.update(rubric_scores)
    return evaluate_capability(
        goal=goal,
        hypotheses=hypotheses,
        baseline_name=baseline_name,
        baseline_score=baseline_score,
        human_scores=human_scores,
        benchmark_scores=benchmark_scores,
        human_rubric_judgment_count=rubric_judgment_count,
        human_rubric_criteria=rubric_criteria,
    )


def load_capability_evaluation_fixtures(
    paths: list[str | Path],
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> list[CapabilityEvaluation]:
    evaluations: list[CapabilityEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_capability_evaluation_fixture(path, goal, hypotheses))
    return evaluations


def load_prospective_evaluation_fixture(
    path: str | Path,
    hypotheses: list[Hypothesis],
) -> ProspectiveEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Prospective evaluation fixture must be a JSON object: {path}")

    hypothesis = _fixture_hypothesis(data, hypotheses)
    implementation_refs = _fixture_string_list(data.get("implementation_refs"), "implementation_refs")
    baseline_metrics = _fixture_metric_map(data.get("baseline_metrics"), "baseline_metrics")
    notes = _fixture_string_list(data.get("notes"), "notes")
    planned = plan_prospective_evaluation(
        hypothesis=hypothesis,
        implementation_refs=implementation_refs,
        baseline_metrics=baseline_metrics,
        notes=notes,
    )
    if "measured_metrics" not in data:
        return planned

    measured_metrics = _fixture_metric_map(data.get("measured_metrics"), "measured_metrics")
    success_metric = _fixture_text(data.get("success_metric"), "")
    if not success_metric:
        raise ValueError("Prospective evaluation fixture with measured_metrics must include success_metric.")
    default_source = "prospective_validation_manifest" if data.get("source_manifest") else "external_fixture"
    return record_prospective_measurement(
        planned,
        measured_metrics,
        success_metric,
        measurement_source=_fixture_text(data.get("measurement_source"), default_source),
        measurement_status=_fixture_text(data.get("measurement_status"), "measured"),
    )


def load_prospective_evaluation_fixtures(
    paths: list[str | Path],
    hypotheses: list[Hypothesis],
) -> list[ProspectiveEvaluation]:
    evaluations: list[ProspectiveEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_prospective_evaluation_fixture(path, hypotheses))
    return evaluations


def run_prospective_validation_manifest(
    manifest_path: str | Path,
    state: RunState,
    *,
    work_dir: str | Path,
) -> dict[str, Any]:
    path = Path(manifest_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Prospective validation manifest must be a JSON object: {path}")

    hypothesis = _fixture_hypothesis(data, state.hypotheses)
    baseline_metrics = _fixture_metric_map(data.get("baseline_metrics"), "baseline_metrics")
    implementation_refs = _fixture_string_list(data.get("implementation_refs"), "implementation_refs")
    success_metric = _fixture_text(data.get("success_metric"), "")
    if not success_metric:
        raise ValueError("Prospective validation manifest must include success_metric.")
    command = _validation_command(data.get("command"), "command")

    output_dir = Path(work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    hypothesis_path = output_dir / "hypothesis.json"
    metrics_path = output_dir / "metrics.json"
    hypothesis_path.write_text(
        json.dumps(
            {
                "goal": state.goal.to_dict(),
                "hypothesis": hypothesis.to_dict(),
                "manifest": str(path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if metrics_path.exists():
        metrics_path.unlink()

    env = os.environ.copy()
    env.update(_validation_env(data.get("env"), "env"))
    env.update(
        {
            "CODE_SCIENTIST_HYPOTHESIS_PATH": str(hypothesis_path),
            "CODE_SCIENTIST_METRICS_PATH": str(metrics_path),
        }
    )
    completed = subprocess.run(
        command,
        cwd=_validation_cwd(data.get("cwd"), path),
        env=env,
        capture_output=True,
        text=True,
        timeout=_validation_timeout(data.get("timeout_seconds", 300)),
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise ValueError(
            f"Prospective validation command failed with exit code {completed.returncode}{detail}"
        )
    measured_metrics, command_notes = _validation_metrics(metrics_path, completed.stdout)
    return {
        "hypothesis_id": hypothesis.id,
        "implementation_refs": implementation_refs,
        "baseline_metrics": baseline_metrics,
        "measured_metrics": measured_metrics,
        "success_metric": success_metric,
        "measurement_source": _fixture_text(data.get("measurement_source"), "prospective_validation_manifest"),
        "measurement_status": _fixture_text(data.get("measurement_status"), "measured"),
        "notes": [
            *_fixture_string_list(data.get("notes"), "notes"),
            *command_notes,
        ],
        "source_manifest": str(path),
    }


def load_feedback_loop_evaluation_fixture(path: str | Path) -> FeedbackLoopEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Feedback-loop evaluation fixture must be a JSON object: {path}")

    cycle = int(_fixture_float(data.get("cycle"), "cycle"))
    source_meta_review_id = _fixture_text(data.get("source_meta_review_id"), "external_feedback_loop")
    feedback_agents = _fixture_string_list(data.get("feedback_agents"), "feedback_agents")
    feedback_item_count = int(_fixture_float(data.get("feedback_item_count"), "feedback_item_count"))
    adopted_feedback_count = int(_fixture_float(data.get("adopted_feedback_count"), "adopted_feedback_count"))
    if feedback_item_count < 0 or adopted_feedback_count < 0:
        raise ValueError("Feedback-loop fixture counts must be non-negative.")
    baseline_quality = _fixture_metric_map(data.get("baseline_quality"), "baseline_quality")
    observed_quality = _fixture_metric_map(data.get("observed_quality"), "observed_quality")
    deltas = {
        metric: round(observed_quality[metric] - baseline, 3)
        for metric, baseline in baseline_quality.items()
        if metric in observed_quality
    }
    artifact_refs = _fixture_string_list(data.get("artifact_refs"), "artifact_refs")
    measurement_source = _fixture_text(data.get("measurement_source"), "external_fixture")
    summary = _fixture_text(data.get("summary"), "External feedback-loop measurement fixture.")
    identity = (
        f"{path}:{cycle}:{source_meta_review_id}:{feedback_agents}:"
        f"{feedback_item_count}:{adopted_feedback_count}:{baseline_quality}:{observed_quality}"
    )
    return FeedbackLoopEvaluation(
        id=stable_id("feedback-loop", identity),
        cycle=cycle,
        source_meta_review_id=source_meta_review_id,
        feedback_agents=feedback_agents,
        feedback_item_count=feedback_item_count,
        adopted_feedback_count=adopted_feedback_count,
        adoption_rate=_rate(adopted_feedback_count, feedback_item_count),
        baseline_quality=baseline_quality,
        observed_quality=observed_quality,
        deltas=deltas,
        artifact_refs=artifact_refs,
        summary=summary,
        measurement_source=measurement_source,
        measurement_status=_fixture_text(data.get("measurement_status"), "measured"),
    )


def load_feedback_loop_evaluation_fixtures(paths: list[str | Path]) -> list[FeedbackLoopEvaluation]:
    evaluations: list[FeedbackLoopEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_feedback_loop_evaluation_fixture(path))
    return evaluations


def build_feedback_loop_review_packet(
    data: dict[str, Any],
    seed: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("Feedback-loop review packet spec must be a JSON object.")
    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Feedback-loop review packet spec must include a non-empty review_items list.")

    cycle = int(_fixture_float(data.get("cycle"), "cycle"))
    source_meta_review_id = _fixture_text(data.get("source_meta_review_id"), "external_feedback_loop_review")
    feedback_agents = _fixture_string_list(data.get("feedback_agents"), "feedback_agents")
    feedback_item_count = _optional_fixture_int(
        data.get("feedback_item_count"),
        "feedback_item_count",
        len(raw_items),
    )
    adopted_feedback_count = _optional_fixture_int(
        data.get("adopted_feedback_count"),
        "adopted_feedback_count",
        0,
    )
    metrics = _fixture_string_list(data.get("metrics"), "metrics")
    if not metrics:
        raise ValueError("Feedback-loop review packet spec must include metrics.")
    artifact_refs = _fixture_string_list(data.get("artifact_refs"), "artifact_refs")
    measurement_source = _fixture_text(data.get("measurement_source"), "blind_review")
    common = {
        "cycle": cycle,
        "source_meta_review_id": source_meta_review_id,
        "feedback_agents": feedback_agents,
        "feedback_item_count": feedback_item_count,
        "adopted_feedback_count": adopted_feedback_count,
        "measurement_source": measurement_source,
        "artifact_refs": artifact_refs,
        "metrics": metrics,
    }
    packet_items: list[dict[str, Any]] = []
    template_items: list[dict[str, Any]] = []
    answer_items: dict[str, dict[str, str]] = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        if "baseline_artifact" not in raw_item or "observed_artifact" not in raw_item:
            raise ValueError(f"review_items[{index}] must include baseline_artifact and observed_artifact.")
        baseline_label, observed_label = _blind_arm_labels(seed, item_id)
        arms = {
            baseline_label: raw_item["baseline_artifact"],
            observed_label: raw_item["observed_artifact"],
        }
        packet_item = {
            "item_id": item_id,
            "arms": {label: arms[label] for label in ("arm_a", "arm_b")},
        }
        prompt = _fixture_text(raw_item.get("prompt"), "")
        if prompt:
            packet_item["prompt"] = prompt
        packet_items.append(packet_item)
        template_items.append(
            {
                "item_id": item_id,
                "scores": {
                    "arm_a": {metric: None for metric in metrics},
                    "arm_b": {metric: None for metric in metrics},
                },
            }
        )
        answer_items[item_id] = {
            "baseline_label": baseline_label,
            "observed_label": observed_label,
        }

    packet = {
        **common,
        "instructions": _fixture_text(
            data.get("instructions"),
            "Score each anonymous arm without using the private answer key.",
        ),
        "review_items": packet_items,
    }
    answer_key = {
        **common,
        "answer_key": answer_items,
    }
    score_template = {
        **common,
        "review_items": template_items,
    }
    return packet, answer_key, score_template


def build_capability_review_packet(
    data: dict[str, Any],
    seed: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("Capability review packet spec must be a JSON object.")
    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Capability review packet spec must include a non-empty review_items list.")

    goal_id = _fixture_text(data.get("goal_id"), "capability-goal")
    objective = _fixture_text(data.get("objective"), "")
    baseline_name = _fixture_text(data.get("baseline_name"), "baseline")
    metrics = _fixture_string_list(data.get("metrics"), "metrics")
    if not metrics:
        raise ValueError("Capability review packet spec must include metrics.")
    artifact_refs = _fixture_string_list(data.get("artifact_refs"), "artifact_refs")
    common = {
        "goal_id": goal_id,
        "objective": objective,
        "baseline_name": baseline_name,
        "artifact_refs": artifact_refs,
        "metrics": metrics,
    }
    packet_items: list[dict[str, Any]] = []
    template_items: list[dict[str, Any]] = []
    answer_items: dict[str, dict[str, str]] = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        if "baseline_artifact" not in raw_item or "code_scientist_artifact" not in raw_item:
            raise ValueError(
                f"review_items[{index}] must include baseline_artifact and code_scientist_artifact."
            )
        baseline_label, code_scientist_label = _blind_arm_labels(seed, item_id)
        arms = {
            baseline_label: raw_item["baseline_artifact"],
            code_scientist_label: raw_item["code_scientist_artifact"],
        }
        packet_item = {
            "item_id": item_id,
            "arms": {label: arms[label] for label in ("arm_a", "arm_b")},
        }
        prompt = _fixture_text(raw_item.get("prompt"), "")
        if prompt:
            packet_item["prompt"] = prompt
        packet_items.append(packet_item)
        template_items.append(
            {
                "item_id": item_id,
                "scores": {
                    "arm_a": {metric: None for metric in metrics},
                    "arm_b": {metric: None for metric in metrics},
                },
            }
        )
        hypothesis_id = _fixture_text(
            raw_item.get("hypothesis_id"),
            _artifact_hypothesis_id(raw_item["code_scientist_artifact"], item_id),
        )
        answer_items[item_id] = {
            "baseline_label": baseline_label,
            "code_scientist_label": code_scientist_label,
            "hypothesis_id": hypothesis_id,
        }

    packet = {
        **common,
        "instructions": _fixture_text(
            data.get("instructions"),
            "Score each anonymous arm against the capability rubric without using the private answer key.",
        ),
        "review_items": packet_items,
    }
    answer_key = {
        **common,
        "answer_key": answer_items,
    }
    score_template = {
        **common,
        "review_items": template_items,
    }
    return packet, answer_key, score_template


def build_preference_review_packet(
    data: dict[str, Any],
    seed: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("Preference review packet spec must be a JSON object.")
    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Preference review packet spec must include a non-empty review_items list.")

    goal_id = _fixture_text(data.get("goal_id"), "preference-goal")
    objective = _fixture_text(data.get("objective"), "")
    baseline_name = _fixture_text(data.get("baseline_name"), "baseline")
    artifact_refs = _fixture_string_list(data.get("artifact_refs"), "artifact_refs")
    common = {
        "goal_id": goal_id,
        "objective": objective,
        "baseline_name": baseline_name,
        "artifact_refs": artifact_refs,
    }
    packet_items: list[dict[str, Any]] = []
    template_items: list[dict[str, Any]] = []
    answer_items: dict[str, dict[str, str]] = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        if "baseline_artifact" not in raw_item or "code_scientist_artifact" not in raw_item:
            raise ValueError(
                f"review_items[{index}] must include baseline_artifact and code_scientist_artifact."
            )
        baseline_label, code_scientist_label = _blind_arm_labels(seed, item_id)
        arms = {
            baseline_label: raw_item["baseline_artifact"],
            code_scientist_label: raw_item["code_scientist_artifact"],
        }
        packet_item = {
            "item_id": item_id,
            "arms": {label: arms[label] for label in ("arm_a", "arm_b")},
        }
        prompt = _fixture_text(raw_item.get("prompt"), "")
        if prompt:
            packet_item["prompt"] = prompt
        packet_items.append(packet_item)
        template_items.append(
            {
                "item_id": item_id,
                "preferred_arm": None,
                "confidence": None,
            }
        )
        hypothesis_id = _fixture_text(
            raw_item.get("hypothesis_id"),
            _artifact_hypothesis_id(raw_item["code_scientist_artifact"], item_id),
        )
        answer_items[item_id] = {
            "baseline_label": baseline_label,
            "code_scientist_label": code_scientist_label,
            "hypothesis_id": hypothesis_id,
        }

    packet = {
        **common,
        "instructions": _fixture_text(
            data.get("instructions"),
            "Choose the anonymous arm that better satisfies the objective. Use no_preference only when they are equivalent.",
        ),
        "review_items": packet_items,
    }
    answer_key = {
        **common,
        "answer_key": answer_items,
    }
    score_template = {
        **common,
        "review_items": template_items,
    }
    return packet, answer_key, score_template


def load_capability_review_fixture(
    path: str | Path,
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> CapabilityEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Capability review fixture must be a JSON object: {path}")

    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Capability review fixture must include a non-empty review_items list.")

    scale = _fixture_float(data.get("human_rubric_scale", 5), "human_rubric_scale")
    if scale <= 0:
        raise ValueError("human_rubric_scale must be greater than zero.")
    answer_key = _capability_review_answer_key(data.get("answer_key"))
    baseline_name = _fixture_text(data.get("baseline_name"), "single_shot_llm")
    baseline_scores: list[float] = []
    human_score_groups: dict[str, list[float]] = {}
    criteria: set[str] = set()
    judgment_count = 0

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        key_item = answer_key.get(item_id, {})
        baseline_label = _fixture_text(raw_item.get("baseline_label"), key_item.get("baseline_label", ""))
        code_scientist_label = _fixture_text(
            raw_item.get("code_scientist_label"),
            key_item.get("code_scientist_label", ""),
        )
        hypothesis_id = _fixture_text(raw_item.get("hypothesis_id"), key_item.get("hypothesis_id", ""))
        if not baseline_label or not code_scientist_label:
            raise ValueError(
                f"review_items[{index}] must include baseline_label and code_scientist_label."
            )
        if not hypothesis_id:
            raise ValueError(f"review_items[{index}] must include hypothesis_id.")
        raw_scores = raw_item.get("scores")
        if not isinstance(raw_scores, dict):
            raise ValueError(f"review_items[{index}].scores must be a label-to-metrics object.")
        if baseline_label not in raw_scores:
            raise ValueError(f"review_items[{index}] is missing scores for baseline_label {baseline_label}.")
        if code_scientist_label not in raw_scores:
            raise ValueError(
                f"review_items[{index}] is missing scores for code_scientist_label {code_scientist_label}."
            )
        baseline_item_scores = _fixture_metric_map(
            raw_scores[baseline_label],
            f"review_items[{index}].scores.{baseline_label}",
        )
        code_scientist_item_scores = _fixture_metric_map(
            raw_scores[code_scientist_label],
            f"review_items[{index}].scores.{code_scientist_label}",
        )
        shared_metrics = sorted(set(baseline_item_scores) & set(code_scientist_item_scores))
        if not shared_metrics:
            raise ValueError(f"review_items[{index}] must score at least one shared metric.")
        baseline_scores.append(
            _mean(baseline_item_scores[metric] / scale for metric in shared_metrics)
        )
        human_score_groups.setdefault(hypothesis_id, []).append(
            _mean(code_scientist_item_scores[metric] / scale for metric in shared_metrics)
        )
        criteria.update(shared_metrics)
        judgment_count += 1

    human_scores = {
        hypothesis_id: _mean(scores)
        for hypothesis_id, scores in human_score_groups.items()
        if scores
    }
    return evaluate_capability(
        goal=goal,
        hypotheses=hypotheses,
        baseline_name=baseline_name,
        baseline_score=_mean(baseline_scores),
        human_scores=human_scores,
        benchmark_scores={},
        human_rubric_judgment_count=judgment_count,
        human_rubric_criteria=sorted(criteria),
    )


def load_capability_review_fixtures(
    paths: list[str | Path],
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> list[CapabilityEvaluation]:
    evaluations: list[CapabilityEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_capability_review_fixture(path, goal, hypotheses))
    return evaluations


def load_preference_review_fixture(
    path: str | Path,
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> CapabilityEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Preference review fixture must be a JSON object: {path}")

    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Preference review fixture must include a non-empty review_items list.")

    answer_key = _capability_review_answer_key(data.get("answer_key"))
    baseline_name = _fixture_text(data.get("baseline_name"), "single_shot_llm")
    baseline_scores: list[float] = []
    human_score_groups: dict[str, list[float]] = {}
    code_scientist_wins = 0
    judgment_count = 0

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        key_item = answer_key.get(item_id, {})
        baseline_label = _fixture_text(raw_item.get("baseline_label"), key_item.get("baseline_label", ""))
        code_scientist_label = _fixture_text(
            raw_item.get("code_scientist_label"),
            key_item.get("code_scientist_label", ""),
        )
        hypothesis_id = _fixture_text(raw_item.get("hypothesis_id"), key_item.get("hypothesis_id", ""))
        if not baseline_label or not code_scientist_label:
            raise ValueError(
                f"review_items[{index}] must include baseline_label and code_scientist_label."
            )
        if not hypothesis_id:
            raise ValueError(f"review_items[{index}] must include hypothesis_id.")
        preferred_arm = _fixture_text(raw_item.get("preferred_arm"), "")
        baseline_score, code_scientist_score = _preference_scores(
            preferred_arm,
            baseline_label,
            code_scientist_label,
            index,
        )
        baseline_scores.append(baseline_score)
        human_score_groups.setdefault(hypothesis_id, []).append(code_scientist_score)
        if code_scientist_score > baseline_score:
            code_scientist_wins += 1
        judgment_count += 1

    human_scores = {
        hypothesis_id: _mean(scores)
        for hypothesis_id, scores in human_score_groups.items()
        if scores
    }
    return evaluate_capability(
        goal=goal,
        hypotheses=hypotheses,
        baseline_name=baseline_name,
        baseline_score=_mean(baseline_scores),
        human_scores=human_scores,
        benchmark_scores={},
        human_preference_judgment_count=judgment_count,
        human_preference_win_rate=_rate(code_scientist_wins, judgment_count),
    )


def load_preference_review_fixtures(
    paths: list[str | Path],
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
) -> list[CapabilityEvaluation]:
    evaluations: list[CapabilityEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_preference_review_fixture(path, goal, hypotheses))
    return evaluations


def load_feedback_loop_review_fixture(path: str | Path) -> FeedbackLoopEvaluation:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Feedback-loop review fixture must be a JSON object: {path}")

    raw_items = data.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Feedback-loop review fixture must include a non-empty review_items list.")

    baseline_scores: dict[str, list[float]] = {}
    observed_scores: dict[str, list[float]] = {}
    improved_item_count = 0
    answer_key = _feedback_loop_answer_key(data.get("answer_key"))
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"review_items[{index}] must be a JSON object.")
        item_id = _fixture_text(raw_item.get("item_id"), f"item-{index + 1}")
        key_item = answer_key.get(item_id, {})
        baseline_label = _fixture_text(raw_item.get("baseline_label"), key_item.get("baseline_label", ""))
        observed_label = _fixture_text(raw_item.get("observed_label"), key_item.get("observed_label", ""))
        if not baseline_label or not observed_label:
            raise ValueError(f"review_items[{index}] must include baseline_label and observed_label.")
        raw_scores = raw_item.get("scores")
        if not isinstance(raw_scores, dict):
            raise ValueError(f"review_items[{index}].scores must be a label-to-metrics object.")
        if baseline_label not in raw_scores:
            raise ValueError(f"review_items[{index}] is missing scores for baseline_label {baseline_label}.")
        if observed_label not in raw_scores:
            raise ValueError(f"review_items[{index}] is missing scores for observed_label {observed_label}.")
        baseline_item_scores = _fixture_metric_map(
            raw_scores[baseline_label],
            f"review_items[{index}].scores.{baseline_label}",
        )
        observed_item_scores = _fixture_metric_map(
            raw_scores[observed_label],
            f"review_items[{index}].scores.{observed_label}",
        )
        shared_metrics = sorted(set(baseline_item_scores) & set(observed_item_scores))
        if not shared_metrics:
            raise ValueError(f"review_items[{index}] must score at least one shared metric.")
        for metric, value in baseline_item_scores.items():
            baseline_scores.setdefault(metric, []).append(value)
        for metric, value in observed_item_scores.items():
            observed_scores.setdefault(metric, []).append(value)
        mean_item_delta = sum(
            observed_item_scores[metric] - baseline_item_scores[metric]
            for metric in shared_metrics
        ) / len(shared_metrics)
        if mean_item_delta > 0:
            improved_item_count += 1

    cycle = int(_fixture_float(data.get("cycle"), "cycle"))
    source_meta_review_id = _fixture_text(data.get("source_meta_review_id"), "external_feedback_loop_review")
    feedback_agents = _fixture_string_list(data.get("feedback_agents"), "feedback_agents")
    feedback_item_count = _optional_fixture_int(
        data.get("feedback_item_count"),
        "feedback_item_count",
        len(raw_items),
    )
    adopted_feedback_count = _optional_fixture_int(
        data.get("adopted_feedback_count"),
        "adopted_feedback_count",
        improved_item_count,
    )
    if feedback_item_count < 0 or adopted_feedback_count < 0:
        raise ValueError("Feedback-loop review fixture counts must be non-negative.")
    baseline_quality = _mean_metric_groups(baseline_scores)
    observed_quality = _mean_metric_groups(observed_scores)
    deltas = {
        metric: round(observed_quality[metric] - baseline, 3)
        for metric, baseline in baseline_quality.items()
        if metric in observed_quality
    }
    artifact_refs = _fixture_string_list(data.get("artifact_refs"), "artifact_refs")
    measurement_source = _fixture_text(data.get("measurement_source"), "blind_review")
    measurement_status = _fixture_text(data.get("measurement_status"), "measured")
    summary = _fixture_text(
        data.get("summary"),
        f"Blind feedback-loop review aggregated {len(raw_items)} scored item(s).",
    )
    identity = (
        f"{path}:{cycle}:{source_meta_review_id}:{feedback_agents}:"
        f"{feedback_item_count}:{adopted_feedback_count}:{baseline_quality}:{observed_quality}"
    )
    return FeedbackLoopEvaluation(
        id=stable_id("feedback-loop-review", identity),
        cycle=cycle,
        source_meta_review_id=source_meta_review_id,
        feedback_agents=feedback_agents,
        feedback_item_count=feedback_item_count,
        adopted_feedback_count=adopted_feedback_count,
        adoption_rate=_rate(adopted_feedback_count, feedback_item_count),
        baseline_quality=baseline_quality,
        observed_quality=observed_quality,
        deltas=deltas,
        artifact_refs=artifact_refs,
        summary=summary,
        measurement_source=measurement_source,
        measurement_status=measurement_status,
    )


def load_feedback_loop_review_fixtures(paths: list[str | Path]) -> list[FeedbackLoopEvaluation]:
    evaluations: list[FeedbackLoopEvaluation] = []
    for path in paths:
        if str(path).strip():
            evaluations.append(load_feedback_loop_review_fixture(path))
    return evaluations


def assemble_capability_review_fixture(
    score_template_path: str | Path,
    answer_key_path: str | Path,
    *,
    human_rubric_scale: float | None = None,
) -> dict[str, Any]:
    fixture = _review_fixture_with_answer_key(score_template_path, answer_key_path)
    if human_rubric_scale is not None:
        if human_rubric_scale <= 0:
            raise ValueError("human_rubric_scale must be greater than zero.")
        fixture["human_rubric_scale"] = human_rubric_scale
    return fixture


def assemble_preference_review_fixture(
    score_template_path: str | Path,
    answer_key_path: str | Path,
) -> dict[str, Any]:
    return _review_fixture_with_answer_key(score_template_path, answer_key_path)


def assemble_feedback_loop_review_fixture(
    score_template_path: str | Path,
    answer_key_path: str | Path,
) -> dict[str, Any]:
    return _review_fixture_with_answer_key(score_template_path, answer_key_path)


def retrospective_benchmark_fixtures() -> list[BenchmarkResult]:
    return [
        BenchmarkResult(
            id="bench-test-first-repair",
            name="Test-first repair loop",
            source="retrospective:coding_agent_workflows",
            baseline_metrics={"pass_rate": 0.42, "regression_count": 3.0},
            candidate_metrics={"pass_rate": 0.64, "regression_count": 1.0},
            deltas={"pass_rate": 0.22, "regression_count": -2.0},
            success=True,
            notes=["Captures known benefit of reproducing failures before patching."],
        ),
        BenchmarkResult(
            id="bench-retrieval-grounded-context",
            name="Retrieval-grounded context selection",
            source="retrospective:coding_agent_workflows",
            baseline_metrics={"pass_rate": 0.48, "regression_count": 2.0},
            candidate_metrics={"pass_rate": 0.68, "regression_count": 1.0},
            deltas={"pass_rate": 0.2, "regression_count": -1.0},
            success=True,
            notes=["Captures known benefit of selecting relevant source and failure context."],
        ),
        BenchmarkResult(
            id="bench-assumption-audit",
            name="Critic-before-edit assumption audit",
            source="retrospective:coding_agent_workflows",
            baseline_metrics={"pass_rate": 0.46, "regression_count": 2.0},
            candidate_metrics={"pass_rate": 0.6, "regression_count": 1.0},
            deltas={"pass_rate": 0.14, "regression_count": -1.0},
            success=True,
            notes=["Captures known benefit of checking assumptions before editing code."],
        ),
    ]


def plan_prospective_evaluation(
    hypothesis: Hypothesis,
    implementation_refs: list[str],
    baseline_metrics: dict[str, float],
    notes: list[str] | None = None,
) -> ProspectiveEvaluation:
    identity = f"{hypothesis.id}:{','.join(implementation_refs)}:{sorted(baseline_metrics.items())}"
    return ProspectiveEvaluation(
        id=stable_id("prospect", identity),
        hypothesis_id=hypothesis.id,
        status="planned",
        implementation_refs=list(implementation_refs),
        baseline_metrics={key: round(value, 3) for key, value in baseline_metrics.items()},
        measured_metrics={},
        deltas={},
        success=False,
        measurement_source="proxy",
        measurement_status="planned",
        notes=list(notes or []),
    )


def record_prospective_measurement(
    evaluation: ProspectiveEvaluation,
    measured_metrics: dict[str, float],
    success_metric: str,
    *,
    measurement_source: str = "external_fixture",
    measurement_status: str = "measured",
) -> ProspectiveEvaluation:
    measured = {key: round(value, 3) for key, value in measured_metrics.items()}
    deltas = {
        key: round(value - evaluation.baseline_metrics.get(key, 0.0), 3)
        for key, value in measured.items()
    }
    success = deltas.get(success_metric, 0.0) > 0
    return ProspectiveEvaluation(
        id=evaluation.id,
        hypothesis_id=evaluation.hypothesis_id,
        status="measured",
        implementation_refs=evaluation.implementation_refs,
        baseline_metrics=evaluation.baseline_metrics,
        measured_metrics=measured,
        deltas=deltas,
        success=success,
        measurement_source=measurement_source,
        measurement_status=measurement_status,
        notes=evaluation.notes,
    )


def record_scaling_curve_point(
    label: str,
    cycles: int,
    task_count: int,
    tool_budget: int,
    baseline_score: float,
    code_scientist_score: float,
    notes: list[str] | None = None,
) -> ScalingCurvePoint:
    delta = round(code_scientist_score - baseline_score, 3)
    identity = f"{label}:{cycles}:{task_count}:{tool_budget}:{baseline_score}:{code_scientist_score}"
    return ScalingCurvePoint(
        id=stable_id("scale", identity),
        label=label,
        cycles=cycles,
        task_count=task_count,
        tool_budget=tool_budget,
        baseline_score=round(baseline_score, 3),
        code_scientist_score=round(code_scientist_score, 3),
        delta=delta,
        notes=list(notes or []),
    )


def evaluate_capability(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    baseline_name: str,
    baseline_score: float,
    human_scores: dict[str, float] | None = None,
    benchmark_scores: dict[str, float] | None = None,
    human_rubric_judgment_count: int = 0,
    human_rubric_criteria: list[str] | None = None,
    human_preference_judgment_count: int = 0,
    human_preference_win_rate: float = 0.0,
) -> CapabilityEvaluation:
    human_scores = human_scores or {}
    benchmark_scores = benchmark_scores or {}
    ranked = sorted(hypotheses, key=lambda item: item.elo, reverse=True)
    top = ranked[0] if ranked else None
    code_scientist_score = _best_available_score(ranked, human_scores, benchmark_scores)
    elo_human_correlation = _score_correlation(ranked, human_scores)
    elo_benchmark_correlation = _score_correlation(ranked, benchmark_scores)
    beats_baseline = code_scientist_score > baseline_score
    summary = (
        f"Code Scientist {'beats' if beats_baseline else 'does not beat'} baseline "
        f"{baseline_name}: {code_scientist_score:.3f} vs {baseline_score:.3f}."
    )
    identity = (
        f"{goal.id}:{baseline_name}:{baseline_score}:"
        f"{code_scientist_score}:{elo_human_correlation}:{elo_benchmark_correlation}"
    )
    return CapabilityEvaluation(
        id=stable_id("eval", identity),
        baseline_name=baseline_name,
        baseline_score=round(baseline_score, 3),
        code_scientist_score=round(code_scientist_score, 3),
        beats_baseline=beats_baseline,
        top_hypothesis_id=top.id if top else "",
        elo_human_correlation=elo_human_correlation,
        elo_benchmark_correlation=elo_benchmark_correlation,
        candidate_count=len(hypotheses),
        summary=summary,
        human_score_count=_matched_score_count(ranked, human_scores),
        benchmark_score_count=_matched_score_count(ranked, benchmark_scores),
        human_rubric_judgment_count=human_rubric_judgment_count,
        human_rubric_criteria=sorted(set(human_rubric_criteria or [])),
        human_preference_judgment_count=human_preference_judgment_count,
        human_preference_win_rate=round(human_preference_win_rate, 3),
    )


def evaluate_capability_proxy(
    goal: ResearchGoal,
    hypotheses: list[Hypothesis],
    baseline_name: str,
    baseline_score: float,
) -> CapabilityEvaluation:
    ranked = sorted(hypotheses, key=lambda item: item.elo, reverse=True)
    top = ranked[0] if ranked else None
    code_scientist_score = _proxy_capability_score(top) if top else 0.0
    beats_baseline = code_scientist_score > baseline_score
    summary = (
        "Deterministic proxy capability evaluation: Code Scientist "
        f"{'beats' if beats_baseline else 'does not beat'} baseline "
        f"{baseline_name}: {code_scientist_score:.3f} vs {baseline_score:.3f}."
    )
    identity = (
        f"{goal.id}:proxy:{baseline_name}:{baseline_score}:"
        f"{code_scientist_score}:{top.id if top else ''}"
    )
    return CapabilityEvaluation(
        id=stable_id("eval", identity),
        baseline_name=baseline_name,
        baseline_score=round(baseline_score, 3),
        code_scientist_score=round(code_scientist_score, 3),
        beats_baseline=beats_baseline,
        top_hypothesis_id=top.id if top else "",
        elo_human_correlation=0.0,
        elo_benchmark_correlation=0.0,
        candidate_count=len(hypotheses),
        summary=summary,
    )


def summarize_capability_study(
    capability_evaluations: list[CapabilityEvaluation],
    scaling_curve: list[ScalingCurvePoint],
    prospective_evaluations: list[ProspectiveEvaluation],
    feedback_loop_evaluations: list[FeedbackLoopEvaluation] | None = None,
) -> CapabilityStudySummary:
    evaluation_count = len(capability_evaluations)
    score_deltas = [
        evaluation.code_scientist_score - evaluation.baseline_score
        for evaluation in capability_evaluations
    ]
    score_delta_count = len(score_deltas)
    baseline_win_rate = _rate(
        sum(1 for evaluation in capability_evaluations if evaluation.beats_baseline),
        evaluation_count,
    )
    mean_score_delta = _mean(score_deltas)
    raw_score_delta_stddev = _sample_stddev_raw(score_deltas)
    raw_score_delta_standard_error = _standard_error_raw(score_deltas)
    score_delta_stddev = round(raw_score_delta_stddev, 3)
    score_delta_standard_error = round(raw_score_delta_standard_error, 3)
    score_delta_ci_low = round(mean_score_delta - 1.96 * raw_score_delta_standard_error, 3) if score_deltas else 0.0
    score_delta_ci_high = round(mean_score_delta + 1.96 * raw_score_delta_standard_error, 3) if score_deltas else 0.0
    score_delta_effect_size = (
        round(mean_score_delta / raw_score_delta_stddev, 3)
        if raw_score_delta_stddev > 0
        else 0.0
    )
    baseline_win_sign_test_p_value = _sign_test_p_value(score_deltas)
    mean_elo_human_correlation = _mean(
        evaluation.elo_human_correlation for evaluation in capability_evaluations
    )
    mean_elo_benchmark_correlation = _mean(
        evaluation.elo_benchmark_correlation for evaluation in capability_evaluations
    )
    ordered_scaling = sorted(scaling_curve, key=lambda item: (item.cycles, item.task_count, item.tool_budget))
    scaling_delta_trend = 0.0
    if len(ordered_scaling) >= 2:
        scaling_delta_trend = round(ordered_scaling[-1].delta - ordered_scaling[0].delta, 3)
    prospective_count = len(prospective_evaluations)
    prospective_success_rate = _rate(
        sum(1 for evaluation in prospective_evaluations if evaluation.success),
        prospective_count,
    )
    measured_feedback_loops = _measured_external_feedback_loops(feedback_loop_evaluations or [])
    feedback_loop_measurement_count = len(measured_feedback_loops)
    feedback_loop_mean_delta = _mean(
        delta
        for evaluation in measured_feedback_loops
        for delta in evaluation.deltas.values()
    )
    feedback_loop_positive_rate = _rate(
        sum(1 for evaluation in measured_feedback_loops if _mean(evaluation.deltas.values()) > 0),
        feedback_loop_measurement_count,
    )
    feedback_loop_metric_deltas = _feedback_loop_metric_delta_means(measured_feedback_loops)
    summary = (
        f"Capability study summary over {evaluation_count} baseline evaluations: "
        f"win rate {baseline_win_rate:.3f}, mean score delta {mean_score_delta:+.3f}; "
        f"scaling delta trend {scaling_delta_trend:+.3f}; "
        f"prospective success rate {prospective_success_rate:.3f}; "
        f"feedback-loop positive rate {feedback_loop_positive_rate:.3f}."
    )
    identity = (
        f"{evaluation_count}:{baseline_win_rate}:{mean_score_delta}:"
        f"{score_delta_count}:{score_delta_stddev}:{score_delta_standard_error}:"
        f"{score_delta_ci_low}:{score_delta_ci_high}:{score_delta_effect_size}:"
        f"{baseline_win_sign_test_p_value}:"
        f"{len(ordered_scaling)}:{scaling_delta_trend}:{prospective_count}:{prospective_success_rate}:"
        f"{feedback_loop_measurement_count}:{feedback_loop_positive_rate}:{feedback_loop_mean_delta}:"
        f"{feedback_loop_metric_deltas}"
    )
    return CapabilityStudySummary(
        id=stable_id("study", identity),
        evaluation_count=evaluation_count,
        baseline_win_rate=baseline_win_rate,
        mean_score_delta=mean_score_delta,
        score_delta_count=score_delta_count,
        score_delta_stddev=score_delta_stddev,
        score_delta_standard_error=score_delta_standard_error,
        score_delta_ci_low=score_delta_ci_low,
        score_delta_ci_high=score_delta_ci_high,
        score_delta_effect_size=score_delta_effect_size,
        baseline_win_sign_test_p_value=baseline_win_sign_test_p_value,
        mean_elo_human_correlation=mean_elo_human_correlation,
        mean_elo_benchmark_correlation=mean_elo_benchmark_correlation,
        scaling_point_count=len(ordered_scaling),
        scaling_delta_trend=scaling_delta_trend,
        prospective_count=prospective_count,
        prospective_success_rate=prospective_success_rate,
        feedback_loop_measurement_count=feedback_loop_measurement_count,
        feedback_loop_positive_rate=feedback_loop_positive_rate,
        feedback_loop_mean_delta=feedback_loop_mean_delta,
        feedback_loop_metric_deltas=feedback_loop_metric_deltas,
        summary=summary,
    )


def summarize_capability_study_from_states(states: list[RunState]) -> CapabilityStudySummary:
    return summarize_capability_study(
        [
            evaluation
            for state in states
            for evaluation in state.capability_evaluations
        ],
        [
            point
            for state in states
            for point in state.scaling_curve
        ],
        [
            evaluation
            for state in states
            for evaluation in state.prospective_evaluations
        ],
        [
            evaluation
            for state in states
            for evaluation in state.feedback_loop_evaluations
        ],
    )


def audit_capability_study_coverage(states: list[RunState]) -> CapabilityStudyCoverage:
    evaluations = [
        evaluation
        for state in states
        for evaluation in state.capability_evaluations
    ]
    baseline_names = sorted({evaluation.baseline_name for evaluation in evaluations if evaluation.baseline_name})
    unique_goal_count = len({state.goal.objective for state in states if state.goal.objective})
    scaling_point_count = sum(len(state.scaling_curve) for state in states)
    measured_prospective_count = sum(
        1
        for state in states
        for evaluation in state.prospective_evaluations
        if evaluation.status == "measured"
        and evaluation.measurement_status == "measured"
        and evaluation.measurement_source != "proxy"
        and evaluation.measured_metrics
    )
    measured_feedback_loop_count = sum(
        1
        for state in states
        for evaluation in state.feedback_loop_evaluations
        if evaluation.measurement_status == "measured" and evaluation.measurement_source != "proxy"
    )
    safety_evaluation_count = sum(len(state.safety_evaluations) for state in states)
    human_scored_candidate_count = sum(evaluation.human_score_count for evaluation in evaluations)
    benchmark_scored_candidate_count = sum(evaluation.benchmark_score_count for evaluation in evaluations)
    benchmark_result_count = sum(len(state.benchmark_results) for state in states)
    human_rubric_judgment_count = sum(evaluation.human_rubric_judgment_count for evaluation in evaluations)
    human_preference_judgment_count = sum(
        evaluation.human_preference_judgment_count for evaluation in evaluations
    )
    missing_requirements: list[str] = []
    if unique_goal_count < 2:
        missing_requirements.append("multi-goal study")
    if not baseline_names:
        missing_requirements.append("baseline workflow comparisons")
    if human_scored_candidate_count <= 0:
        missing_requirements.append("human rubric scores")
    if human_rubric_judgment_count <= 0:
        missing_requirements.append("criterion-level human rubric judgments")
    if human_preference_judgment_count <= 0:
        missing_requirements.append("human preference judgments")
    if benchmark_scored_candidate_count <= 0 and benchmark_result_count <= 0:
        missing_requirements.append("benchmark scores or benchmark result artifacts")
    if scaling_point_count < 2:
        missing_requirements.append("test-time compute scaling curve")
    if measured_prospective_count <= 0:
        missing_requirements.append("prospective/external validation measurements")
    if measured_feedback_loop_count <= 0:
        missing_requirements.append("external feedback-loop measurement")
    if safety_evaluation_count <= 0:
        missing_requirements.append("safety red-team evaluation")
    passed = not missing_requirements
    summary = (
        "Study coverage is complete for the tracked paper-level evaluation requirements."
        if passed
        else f"Study coverage is incomplete; missing {', '.join(missing_requirements)}."
    )
    identity = (
        f"{len(states)}:{unique_goal_count}:{baseline_names}:{len(evaluations)}:"
        f"{human_scored_candidate_count}:{benchmark_scored_candidate_count}:"
        f"{benchmark_result_count}:{human_rubric_judgment_count}:"
        f"{human_preference_judgment_count}:{scaling_point_count}:"
        f"{measured_prospective_count}:{measured_feedback_loop_count}:"
        f"{safety_evaluation_count}:{missing_requirements}"
    )
    return CapabilityStudyCoverage(
        id=stable_id("coverage", identity),
        run_count=len(states),
        unique_goal_count=unique_goal_count,
        baseline_names=baseline_names,
        capability_evaluation_count=len(evaluations),
        human_scored_candidate_count=human_scored_candidate_count,
        benchmark_scored_candidate_count=benchmark_scored_candidate_count,
        benchmark_result_count=benchmark_result_count,
        human_rubric_judgment_count=human_rubric_judgment_count,
        human_preference_judgment_count=human_preference_judgment_count,
        scaling_point_count=scaling_point_count,
        measured_prospective_count=measured_prospective_count,
        measured_feedback_loop_count=measured_feedback_loop_count,
        safety_evaluation_count=safety_evaluation_count,
        missing_requirements=missing_requirements,
        passed=passed,
        summary=summary,
    )


def _best_available_score(
    ranked: list[Hypothesis],
    human_scores: dict[str, float],
    benchmark_scores: dict[str, float],
) -> float:
    for scores in (human_scores, benchmark_scores):
        matched = [scores[item.id] for item in ranked if item.id in scores]
        if matched:
            return max(matched)
    return 0.0


def _proxy_capability_score(hypothesis: Hypothesis) -> float:
    text = " ".join(
        [
            hypothesis.title,
            hypothesis.claim,
            hypothesis.rationale,
            hypothesis.test_plan.experiment,
            hypothesis.test_plan.success_condition,
            *hypothesis.test_plan.metrics,
        ]
    ).lower()
    score = 0.35
    if hypothesis.evidence_refs:
        score += 0.15
    if hypothesis.test_plan.metrics:
        score += 0.15
    if hypothesis.status == "accepted":
        score += 0.10
    if any(marker in text for marker in ("benchmark", "pass_rate", "regression", "validation")):
        score += 0.10
    score += min(max((hypothesis.elo - 1200.0) / 400.0, 0.0), 1.0) * 0.15
    return round(min(max(score, 0.0), 1.0), 3)


def _matched_score_count(hypotheses: list[Hypothesis], scores: dict[str, float]) -> int:
    return sum(1 for item in hypotheses if item.id in scores)


def _score_correlation(hypotheses: list[Hypothesis], scores: dict[str, float]) -> float:
    pairs = [(item.elo, scores[item.id]) for item in hypotheses if item.id in scores]
    if len(pairs) < 2:
        return 0.0
    elo_values = [item[0] for item in pairs]
    score_values = [item[1] for item in pairs]
    correlation = _pearson(elo_values, score_values)
    return round(correlation, 3)


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((left_item - left_mean) * (right_item - right_mean) for left_item, right_item in zip(left, right))
    left_denominator = sqrt(sum((item - left_mean) ** 2 for item in left))
    right_denominator = sqrt(sum((item - right_mean) ** 2 for item in right))
    denominator = left_denominator * right_denominator
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _mean(values: Any) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(items) / len(items), 3)


def _sample_stddev_raw(values: Any) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    mean = sum(items) / len(items)
    variance = sum((item - mean) ** 2 for item in items) / (len(items) - 1)
    return sqrt(variance)


def _standard_error_raw(values: Any) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    return _sample_stddev_raw(items) / sqrt(len(items))


def _sign_test_p_value(values: Any) -> float:
    items = [item for item in values if item != 0]
    total = len(items)
    if total == 0:
        return 1.0
    wins = sum(1 for item in items if item > 0)
    tail = min(wins, total - wins)
    probability = sum(comb(total, successes) for successes in range(tail + 1)) / (2 ** total)
    return round(min(1.0, 2 * probability), 3)


def _mean_metric_groups(groups: dict[str, list[float]]) -> dict[str, float]:
    return {
        metric: _mean(values)
        for metric, values in sorted(groups.items())
        if values
    }


def _measured_external_feedback_loops(
    evaluations: list[FeedbackLoopEvaluation],
) -> list[FeedbackLoopEvaluation]:
    return [
        evaluation
        for evaluation in evaluations
        if evaluation.measurement_status == "measured"
        and evaluation.measurement_source != "proxy"
        and evaluation.deltas
    ]


def _feedback_loop_metric_delta_means(
    evaluations: list[FeedbackLoopEvaluation],
) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for evaluation in evaluations:
        for metric, delta in evaluation.deltas.items():
            grouped.setdefault(metric, []).append(delta)
    return _mean_metric_groups(grouped)


def _feedback_loop_answer_key(value: object) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("answer_key must be a mapping of item id to labels.")
    answer_key: dict[str, dict[str, str]] = {}
    for item_id, raw_item in value.items():
        if not isinstance(raw_item, dict):
            raise ValueError(f"answer_key.{item_id} must be a JSON object.")
        baseline_label = _fixture_text(raw_item.get("baseline_label"), "")
        observed_label = _fixture_text(raw_item.get("observed_label"), "")
        if not baseline_label or not observed_label:
            raise ValueError(f"answer_key.{item_id} must include baseline_label and observed_label.")
        answer_key[str(item_id)] = {
            "baseline_label": baseline_label,
            "observed_label": observed_label,
        }
    return answer_key


def _capability_review_answer_key(value: object) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("answer_key must be a mapping of item id to labels.")
    answer_key: dict[str, dict[str, str]] = {}
    for item_id, raw_item in value.items():
        if not isinstance(raw_item, dict):
            raise ValueError(f"answer_key.{item_id} must be a JSON object.")
        baseline_label = _fixture_text(raw_item.get("baseline_label"), "")
        code_scientist_label = _fixture_text(raw_item.get("code_scientist_label"), "")
        hypothesis_id = _fixture_text(raw_item.get("hypothesis_id"), "")
        if not baseline_label or not code_scientist_label:
            raise ValueError(
                f"answer_key.{item_id} must include baseline_label and code_scientist_label."
            )
        answer_key_item = {
            "baseline_label": baseline_label,
            "code_scientist_label": code_scientist_label,
        }
        if hypothesis_id:
            answer_key_item["hypothesis_id"] = hypothesis_id
        answer_key[str(item_id)] = answer_key_item
    return answer_key


def _review_fixture_with_answer_key(
    score_template_path: str | Path,
    answer_key_path: str | Path,
) -> dict[str, Any]:
    score_template = json.loads(Path(score_template_path).read_text(encoding="utf-8"))
    answer_key = json.loads(Path(answer_key_path).read_text(encoding="utf-8"))
    if not isinstance(score_template, dict):
        raise ValueError(f"Review score template must be a JSON object: {score_template_path}")
    if not isinstance(answer_key, dict):
        raise ValueError(f"Review answer key must be a JSON object: {answer_key_path}")
    raw_answer_key = answer_key.get("answer_key")
    if not isinstance(raw_answer_key, dict):
        raise ValueError("Review answer key must include an answer_key mapping.")
    raw_items = score_template.get("review_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Review score template must include a non-empty review_items list.")
    return {
        **score_template,
        "answer_key": raw_answer_key,
        "artifact_refs": _merged_artifact_refs(score_template, answer_key),
    }


def _preference_scores(
    preferred_arm: str,
    baseline_label: str,
    code_scientist_label: str,
    index: int,
) -> tuple[float, float]:
    normalized = preferred_arm.strip().lower()
    if normalized == baseline_label:
        return 1.0, 0.0
    if normalized == code_scientist_label:
        return 0.0, 1.0
    if normalized in {"tie", "no_preference", "no preference", "equal"}:
        return 0.5, 0.5
    raise ValueError(
        f"review_items[{index}].preferred_arm must be {baseline_label}, "
        f"{code_scientist_label}, or no_preference."
    )


def _merged_artifact_refs(score_template: dict[str, Any], answer_key: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for value in [score_template.get("artifact_refs"), answer_key.get("artifact_refs")]:
        if isinstance(value, list):
            refs.extend(str(item) for item in value if str(item).strip())
    return list(dict.fromkeys(refs))


def _blind_arm_labels(seed: str, item_id: str) -> tuple[str, str]:
    digest = stable_id("blind", f"{seed}:{item_id}")
    if int(digest.rsplit("-", 1)[-1][-1], 16) % 2 == 0:
        return "arm_a", "arm_b"
    return "arm_b", "arm_a"


def _artifact_hypothesis_id(value: object, fallback: str) -> str:
    if isinstance(value, dict):
        return _fixture_text(value.get("hypothesis_id"), fallback)
    return fallback


def _validation_command(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list of strings.")
    command = [str(item) for item in value if isinstance(item, str) and item.strip()]
    if len(command) != len(value):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return command


def _validation_env(value: object, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return {str(key): str(raw_value) for key, raw_value in value.items()}


def _validation_cwd(value: object, manifest_path: Path) -> Path:
    if value is None or not str(value).strip():
        return manifest_path.parent
    path = Path(str(value))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path


def _validation_timeout(value: object) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive.")
    return timeout


def _validation_metrics(metrics_path: Path, stdout: str) -> tuple[dict[str, float], list[str]]:
    raw_text = ""
    if metrics_path.exists():
        raw_text = metrics_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raw_text = stdout.strip()
    if not raw_text:
        raise ValueError("Prospective validation command did not produce metrics JSON.")
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Prospective validation metrics must be a JSON object.")
    raw_metrics = data.get("metrics")
    metric_source = raw_metrics if isinstance(raw_metrics, dict) else data
    measured_metrics = _fixture_metric_map(metric_source, "measured_metrics")
    return measured_metrics, _fixture_string_list(data.get("notes"), "notes")


def _score_map(value: object, label: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping of hypothesis id to score.")
    return {str(key): _fixture_float(score, f"{label}.{key}") for key, score in value.items()}


def _fixture_hypothesis(data: dict[str, Any], hypotheses: list[Hypothesis]) -> Hypothesis:
    hypothesis_id = _fixture_text(data.get("hypothesis_id"), "")
    if hypothesis_id:
        for hypothesis in hypotheses:
            if hypothesis.id == hypothesis_id:
                return hypothesis
        raise ValueError(f"Prospective evaluation fixture references unknown hypothesis_id: {hypothesis_id}")

    selector = data.get("hypothesis_selector")
    terms = _selector_terms(selector)
    if not terms:
        raise ValueError("Prospective evaluation fixture must include hypothesis_id or hypothesis_selector.")
    matches = [
        hypothesis
        for hypothesis in hypotheses
        if all(term in _hypothesis_text(hypothesis) for term in terms)
    ]
    if not matches:
        raise ValueError("Prospective evaluation fixture selector did not match any hypothesis.")
    return sorted(matches, key=lambda item: item.elo, reverse=True)[0]


def _selector_terms(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    if not isinstance(value, dict):
        return []
    return _rule_terms(value.get("contains"))


def _fixture_string_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of strings.")
    return [str(item) for item in value if str(item).strip()]


def _fixture_metric_map(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty metrics object.")
    return {str(key): _fixture_float(raw_value, f"{label}.{key}") for key, raw_value in value.items()}


def _scores_from_rules(hypotheses: list[Hypothesis], value: object) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError("score rules must be a list.")

    scores: dict[str, float] = {}
    for index, raw_rule in enumerate(value):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"score rule {index} must be a JSON object.")
        terms = _rule_terms(raw_rule.get("contains"))
        score = _fixture_float(raw_rule.get("score"), f"score rule {index}.score")
        if not terms:
            continue
        for hypothesis in hypotheses:
            text = _hypothesis_text(hypothesis)
            if all(term.lower() in text for term in terms):
                scores[hypothesis.id] = max(scores.get(hypothesis.id, score), score)
    return scores


def _scores_from_human_rubric_judgments(value: object, scale_value: object) -> tuple[dict[str, float], int, list[str]]:
    if value is None:
        return {}, 0, []
    if not isinstance(value, list):
        raise ValueError("human_rubric_judgments must be a list.")
    scale = _fixture_float(scale_value, "human_rubric_scale")
    if scale <= 0:
        raise ValueError("human_rubric_scale must be greater than zero.")

    scores_by_hypothesis: dict[str, list[float]] = {}
    criteria: set[str] = set()
    judgment_count = 0
    for index, raw_judgment in enumerate(value):
        if not isinstance(raw_judgment, dict):
            raise ValueError(f"human rubric judgment {index} must be a JSON object.")
        hypothesis_id = _fixture_text(raw_judgment.get("hypothesis_id"), "")
        raw_scores = raw_judgment.get("scores")
        if not hypothesis_id:
            raise ValueError(f"human rubric judgment {index} is missing hypothesis_id.")
        if not isinstance(raw_scores, dict) or not raw_scores:
            raise ValueError(f"human rubric judgment {index} must include criterion scores.")
        criterion_scores = [
            _fixture_float(score, f"human rubric judgment {index}.{criterion}") / scale
            for criterion, score in raw_scores.items()
            if str(criterion).strip()
        ]
        if not criterion_scores:
            raise ValueError(f"human rubric judgment {index} must include named criterion scores.")
        criteria.update(str(criterion).strip() for criterion in raw_scores if str(criterion).strip())
        scores_by_hypothesis.setdefault(hypothesis_id, []).append(sum(criterion_scores) / len(criterion_scores))
        judgment_count += 1

    scores = {
        hypothesis_id: round(sum(values) / len(values), 3)
        for hypothesis_id, values in scores_by_hypothesis.items()
        if values
    }
    return scores, judgment_count, sorted(criteria)


def _rule_terms(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def _hypothesis_text(hypothesis: Hypothesis) -> str:
    return " ".join(
        [
            hypothesis.title,
            hypothesis.claim,
            hypothesis.rationale,
            *hypothesis.assumptions,
            *hypothesis.risks,
        ]
    ).lower()


def _fixture_text(value: Any, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _fixture_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc


def _optional_fixture_int(value: object, label: str, fallback: int) -> int:
    if value is None:
        return fallback
    return int(_fixture_float(value, label))
