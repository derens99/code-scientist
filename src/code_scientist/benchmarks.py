from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_scientist.models import BenchmarkResult, stable_id


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


def _metrics(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"Benchmark fixture must include a {label} metrics object.")
    metrics: dict[str, float] = {}
    for key, raw_value in value.items():
        parsed = float(raw_value)
        metrics[str(key)] = parsed
    return metrics


def _is_successful(deltas: dict[str, float]) -> bool:
    return deltas["pass_rate"] >= 0 and deltas["regression_count"] <= 0
