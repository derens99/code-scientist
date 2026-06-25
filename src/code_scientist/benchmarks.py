from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from code_scientist.models import BenchmarkResult, Hypothesis, stable_id


REQUIRED_BENCHMARK_METRICS = ("pass_rate", "regression_count", "tool_calls", "wall_time", "cost")


def load_benchmark_fixture(path: str | Path) -> BenchmarkResult:
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    baseline = _metrics(data.get("baseline"), "baseline")
    candidate = _metrics(data.get("candidate"), "candidate")
    missing = [
        metric
        for metric in REQUIRED_BENCHMARK_METRICS
        if metric not in baseline or metric not in candidate
    ]
    if missing:
        raise ValueError(f"Missing benchmark metrics: {', '.join(missing)}")

    deltas = {
        metric: round(candidate[metric] - baseline[metric], 6)
        for metric in REQUIRED_BENCHMARK_METRICS
    }
    name = str(data.get("name") or fixture_path.stem)
    return BenchmarkResult(
        id=stable_id("bench", f"{fixture_path}:{name}:{baseline}:{candidate}"),
        name=name,
        source=str(fixture_path),
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        deltas=deltas,
        success=_is_successful(deltas),
        notes=[str(item) for item in data.get("notes", [])],
    )


def run_benchmark_suite(path: str | Path, hypotheses: list[Hypothesis]) -> BenchmarkResult:
    suite_path = Path(path)
    data = _load_suite_data(suite_path)
    baseline = _metrics(data.get("baseline"), "baseline")
    missing = [metric for metric in REQUIRED_BENCHMARK_METRICS if metric not in baseline]
    if missing:
        raise ValueError(f"Missing benchmark metrics: {', '.join(missing)}")
    raw_cases = _benchmark_cases(data)
    case_cost = _optional_metrics(data.get("case_cost"), "case_cost")
    candidate, outcomes = _score_benchmark_cases(raw_cases, hypotheses, case_cost)
    notes = [f"{case_id}: {outcome}" for case_id, outcome in outcomes.items()]
    deltas = {
        metric: round(candidate[metric] - baseline[metric], 6)
        for metric in REQUIRED_BENCHMARK_METRICS
    }
    name = str(data.get("name") or suite_path.stem)
    return BenchmarkResult(
        id=stable_id("bench-suite", f"{suite_path}:{name}:{baseline}:{candidate}:{notes}"),
        name=name,
        source=str(suite_path),
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        deltas=deltas,
        success=_is_successful(deltas),
        notes=notes,
    )


def run_benchmark_suite_comparison(
    path: str | Path,
    baseline_hypotheses: list[Hypothesis],
    candidate_hypotheses: list[Hypothesis],
    *,
    baseline_name: str = "baseline",
    candidate_name: str = "code_scientist",
) -> BenchmarkResult:
    suite_path = Path(path)
    data = _load_suite_data(suite_path)
    raw_cases = _benchmark_cases(data)
    baseline_cost_value = data["baseline_case_cost"] if "baseline_case_cost" in data else data.get("case_cost")
    candidate_cost_value = data["candidate_case_cost"] if "candidate_case_cost" in data else data.get("case_cost")
    baseline_cost = _optional_metrics(baseline_cost_value, "baseline_case_cost")
    candidate_cost = _optional_metrics(candidate_cost_value, "candidate_case_cost")
    baseline, baseline_outcomes = _score_benchmark_cases(
        raw_cases,
        baseline_hypotheses,
        baseline_cost,
    )
    candidate, candidate_outcomes = _score_benchmark_cases(
        raw_cases,
        candidate_hypotheses,
        candidate_cost,
    )
    baseline_label = str(baseline_name or "baseline").strip() or "baseline"
    candidate_label = str(candidate_name or "code_scientist").strip() or "code_scientist"
    notes = [
        f"{case_id}: {baseline_label} {baseline_outcomes[case_id]}; "
        f"{candidate_label} {candidate_outcomes[case_id]}"
        for case_id in baseline_outcomes
    ]
    deltas = {
        metric: round(candidate[metric] - baseline[metric], 6)
        for metric in REQUIRED_BENCHMARK_METRICS
    }
    name = str(data.get("name") or suite_path.stem)
    return BenchmarkResult(
        id=stable_id(
            "bench-suite-compare",
            f"{suite_path}:{name}:{baseline_label}:{candidate_label}:{baseline}:{candidate}:{notes}",
        ),
        name=name,
        source=str(suite_path),
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        deltas=deltas,
        success=_is_successful(deltas),
        notes=notes,
    )


def run_external_benchmark_comparison(
    path: str | Path,
    baseline_hypotheses: list[Hypothesis],
    candidate_hypotheses: list[Hypothesis],
    *,
    work_dir: str | Path,
) -> BenchmarkResult:
    manifest_path = Path(path)
    data = _load_suite_data(manifest_path)
    output_dir = Path(work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline, baseline_notes = _run_external_benchmark_arm(
        "baseline",
        data,
        manifest_path,
        baseline_hypotheses,
        output_dir,
    )
    candidate, candidate_notes = _run_external_benchmark_arm(
        "candidate",
        data,
        manifest_path,
        candidate_hypotheses,
        output_dir,
    )
    deltas = {
        metric: round(candidate[metric] - baseline[metric], 6)
        for metric in REQUIRED_BENCHMARK_METRICS
    }
    name = str(data.get("name") or manifest_path.stem)
    notes = [
        *_external_note_list(data.get("notes")),
        "baseline external command completed",
        *baseline_notes,
        "candidate external command completed",
        *candidate_notes,
    ]
    return BenchmarkResult(
        id=stable_id(
            "bench-external",
            f"{manifest_path}:{name}:{baseline}:{candidate}:{notes}",
        ),
        name=name,
        source=str(manifest_path),
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        deltas=deltas,
        success=_is_successful(deltas),
        notes=notes,
    )


def summarize_benchmark_comparison_study(results: list[BenchmarkResult]) -> dict[str, float | int]:
    count = len(results)
    if count == 0:
        return {
            "comparison_count": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "mean_pass_rate_delta": 0.0,
            "total_regression_delta": 0.0,
            "mean_tool_calls_delta": 0.0,
            "mean_wall_time_delta": 0.0,
            "mean_cost_delta": 0.0,
        }

    success_count = sum(1 for result in results if result.success)
    return {
        "comparison_count": count,
        "success_count": success_count,
        "success_rate": round(success_count / count, 6),
        "mean_pass_rate_delta": _mean_delta(results, "pass_rate"),
        "total_regression_delta": round(sum(result.deltas.get("regression_count", 0.0) for result in results), 6),
        "mean_tool_calls_delta": _mean_delta(results, "tool_calls"),
        "mean_wall_time_delta": _mean_delta(results, "wall_time"),
        "mean_cost_delta": _mean_delta(results, "cost"),
    }


def _load_suite_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Benchmark suite must be a JSON object: {path}")
    return data


def _benchmark_cases(data: dict[str, Any]) -> list[Any]:
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Benchmark suite must include a non-empty cases list.")
    return raw_cases


def _score_benchmark_cases(
    raw_cases: list[Any],
    hypotheses: list[Hypothesis],
    case_cost: dict[str, float],
) -> tuple[dict[str, float], dict[str, str]]:
    passed = 0
    outcomes: dict[str, str] = {}
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"cases[{index}] must be a JSON object.")
        case_id = str(raw_case.get("id") or f"case-{index + 1}").strip()
        required_terms = _term_list(raw_case.get("required_terms"), f"cases[{index}].required_terms")
        forbidden_terms = _term_list(raw_case.get("forbidden_terms"), f"cases[{index}].forbidden_terms")
        if not required_terms:
            raise ValueError(f"cases[{index}] must include required_terms.")
        matched = _matching_hypothesis(hypotheses, required_terms, forbidden_terms)
        if matched:
            passed += 1
            outcomes[case_id] = f"passed via {matched.id}"
        else:
            outcomes[case_id] = "failed"

    case_count = len(raw_cases)
    return (
        {
            "pass_rate": round(passed / case_count, 6),
            "regression_count": float(case_count - passed),
            "tool_calls": float(case_cost.get("tool_calls", 0.0) * case_count),
            "wall_time": float(case_cost.get("wall_time", 0.0) * case_count),
            "cost": float(case_cost.get("cost", 0.0) * case_count),
        },
        outcomes,
    )


def _run_external_benchmark_arm(
    arm: str,
    data: dict[str, Any],
    manifest_path: Path,
    hypotheses: list[Hypothesis],
    work_dir: Path,
) -> tuple[dict[str, float], list[str]]:
    spec = _external_arm_spec(data, arm)
    command = _external_command(spec.get("command"), f"{arm}.command")
    hypotheses_path = work_dir / f"{arm}-hypotheses.json"
    metrics_path = work_dir / f"{arm}-metrics.json"
    hypotheses_path.write_text(
        json.dumps(
            {
                "arm": arm,
                "hypotheses": [hypothesis.to_dict() for hypothesis in hypotheses],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if metrics_path.exists():
        metrics_path.unlink()

    env = os.environ.copy()
    env.update(_external_env(data.get("env"), "env"))
    env.update(_external_env(spec.get("env"), f"{arm}.env"))
    env.update(
        {
            "CODE_SCIENTIST_ARM": arm,
            "CODE_SCIENTIST_HYPOTHESES_PATH": str(hypotheses_path),
            "CODE_SCIENTIST_METRICS_PATH": str(metrics_path),
        }
    )
    completed = subprocess.run(
        command,
        cwd=_external_cwd(spec.get("cwd", data.get("cwd")), manifest_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=_external_timeout(spec.get("timeout_seconds", data.get("timeout_seconds", 300))),
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise ValueError(f"External benchmark command failed for {arm} with exit code {completed.returncode}{detail}")
    return _external_metrics(metrics_path, completed.stdout, arm)


def _external_arm_spec(data: dict[str, Any], arm: str) -> dict[str, Any]:
    value = data.get(arm)
    if not isinstance(value, dict):
        raise ValueError(f"External benchmark manifest must include a {arm} object.")
    return value


def _external_command(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return list(value)


def _external_env(value: Any, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return {str(key): str(raw_value) for key, raw_value in value.items()}


def _external_cwd(value: Any, manifest_path: Path) -> Path:
    if value is None or not str(value).strip():
        return manifest_path.parent
    path = Path(str(value))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path


def _external_timeout(value: Any) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive.")
    return timeout


def _external_metrics(metrics_path: Path, stdout: str, label: str) -> tuple[dict[str, float], list[str]]:
    if metrics_path.exists() and metrics_path.read_text(encoding="utf-8").strip():
        raw_text = metrics_path.read_text(encoding="utf-8")
    else:
        raw_text = stdout.strip()
    if not raw_text:
        raise ValueError(f"External benchmark command for {label} did not produce metrics JSON.")
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError(f"External benchmark metrics for {label} must be a JSON object.")
    metric_source = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
    metrics = _required_external_metrics(metric_source, label)
    notes = _external_note_list(data.get("notes"))
    return metrics, notes


def _required_external_metrics(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"External benchmark metrics for {label} must be a JSON object.")
    missing = [metric for metric in REQUIRED_BENCHMARK_METRICS if metric not in value]
    if missing:
        raise ValueError(f"Missing benchmark metrics: {', '.join(missing)}")
    return {
        metric: float(value[metric])
        for metric in REQUIRED_BENCHMARK_METRICS
    }


def _external_note_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _metrics(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"Benchmark fixture must include a {label} metrics object.")
    metrics: dict[str, float] = {}
    for key, raw_value in value.items():
        parsed = float(raw_value)
        metrics[str(key)] = parsed
    return metrics


def _optional_metrics(value: Any, label: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a metrics object.")
    return {str(key): float(raw_value) for key, raw_value in value.items()}


def _term_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a string or list of strings.")
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _matching_hypothesis(
    hypotheses: list[Hypothesis],
    required_terms: list[str],
    forbidden_terms: list[str],
) -> Hypothesis | None:
    for hypothesis in hypotheses:
        text = _hypothesis_text(hypothesis)
        if all(term in text for term in required_terms) and not any(term in text for term in forbidden_terms):
            return hypothesis
    return None


def _mean_delta(results: list[BenchmarkResult], metric: str) -> float:
    if not results:
        return 0.0
    return round(sum(result.deltas.get(metric, 0.0) for result in results) / len(results), 6)


def _hypothesis_text(hypothesis: Hypothesis) -> str:
    return " ".join(
        [
            hypothesis.id,
            hypothesis.title,
            hypothesis.claim,
            hypothesis.rationale,
            *hypothesis.assumptions,
            *hypothesis.evidence_refs,
            hypothesis.test_plan.experiment,
            *hypothesis.test_plan.metrics,
            hypothesis.test_plan.success_condition,
            *hypothesis.risks,
        ]
    ).lower()


def _is_successful(deltas: dict[str, float]) -> bool:
    return deltas["pass_rate"] >= 0 and deltas["regression_count"] <= 0
