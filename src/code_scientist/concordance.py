from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from code_scientist.models import Hypothesis

_DEFAULT_ANSWER_PATTERN = r"answer\s*[:=]\s*([A-Za-z0-9_.-]+)"


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
