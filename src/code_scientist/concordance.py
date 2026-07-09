from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from code_scientist.models import EloConcordanceResult, Hypothesis, stable_id

_DEFAULT_ANSWER_PATTERN = r"answer\s*[:=]\s*([A-Za-z0-9_.-]+)"
_INACTIVE_STATUSES = {"merged_duplicate", "quarantined"}


@dataclass(frozen=True)
class ObjectiveBenchmark:
    name: str
    question: str
    answer: str
    answer_pattern: str = _DEFAULT_ANSWER_PATTERN


def load_objective_benchmark(path: str | Path) -> ObjectiveBenchmark:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for field_name in ("name", "question", "answer"):
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Objective benchmark requires non-empty string field '{field_name}'.")
    return ObjectiveBenchmark(
        name=data["name"].strip(),
        question=data["question"].strip(),
        answer=data["answer"].strip(),
        answer_pattern=data.get("answer_pattern") or _DEFAULT_ANSWER_PATTERN,
    )


def grade_hypotheses(
    benchmark: ObjectiveBenchmark,
    hypotheses: list[Hypothesis],
    grades: dict[str, bool] | None = None,
) -> dict[str, bool]:
    pattern = re.compile(benchmark.answer_pattern, re.IGNORECASE)
    graded: dict[str, bool] = {}
    for hypothesis in hypotheses:
        text = f"{hypothesis.title} {hypothesis.claim} {hypothesis.rationale}"
        match = pattern.search(text)
        if match:
            graded[hypothesis.id] = match.group(1).strip().lower() == benchmark.answer.lower()
    for hypothesis_id, verdict in (grades or {}).items():
        graded[hypothesis_id] = bool(verdict)
    return graded


def compute_elo_concordance(
    benchmark_name: str,
    question: str,
    hypotheses: list[Hypothesis],
    correctness: dict[str, bool],
) -> EloConcordanceResult:
    active = [item for item in hypotheses if item.status not in _INACTIVE_STATUSES]
    graded = sorted(
        (item for item in active if item.id in correctness),
        key=lambda item: item.elo,
        reverse=True,
    )
    ungraded_count = len(active) - len(graded)
    accuracy = (
        round(sum(1 for item in graded if correctness[item.id]) / len(graded), 3) if graded else 0.0
    )
    top = graded[0] if graded else None

    correct_elos = [item.elo for item in graded if correctness[item.id]]
    incorrect_elos = [item.elo for item in graded if not correctness[item.id]]
    if correct_elos and incorrect_elos:
        score = sum(
            1.0 if good > bad else 0.5 if good == bad else 0.0
            for good in correct_elos
            for bad in incorrect_elos
        )
        concordance_index = round(score / (len(correct_elos) * len(incorrect_elos)), 3)
    else:
        concordance_index = 0.5

    buckets: list[dict[str, float]] = []
    bucket_count = min(4, len(graded))
    if bucket_count:
        size, remainder = divmod(len(graded), bucket_count)
        start = 0
        for index in range(bucket_count):
            end = start + size + (1 if index < remainder else 0)
            members = graded[start:end]
            buckets.append(
                {
                    "bucket": float(index),
                    "elo_max": round(members[0].elo, 3),
                    "elo_min": round(members[-1].elo, 3),
                    "count": float(len(members)),
                    "accuracy": round(
                        sum(1 for item in members if correctness[item.id]) / len(members), 3
                    ),
                }
            )
            start = end

    identity = f"{benchmark_name}:{question}:{len(graded)}:{accuracy}:{concordance_index}"
    return EloConcordanceResult(
        id=stable_id("conc", identity),
        benchmark_name=benchmark_name,
        question=question,
        graded_count=len(graded),
        ungraded_count=ungraded_count,
        overall_accuracy=accuracy,
        top_hypothesis_id=top.id if top else "",
        top_hypothesis_correct=bool(top and correctness[top.id]),
        concordance_index=concordance_index,
        buckets=buckets,
        notes=[],
    )
