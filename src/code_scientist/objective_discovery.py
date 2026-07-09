from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "runs",
}
_CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".sh",
}
_TODO_PATTERN = re.compile(r"(?:#|//|/\*|<!--)\s*(?:TODO|FIXME|HACK|XXX)\b[:\s-]*(.+)", re.IGNORECASE)
_DOC_GAP_TERMS = (
    "not yet implemented",
    "unimplemented",
    "not implemented",
    "future work",
    "known gap",
    "still missing",
    "needs implementation",
    "left as a stub",
    "is a stub",
)
_KIND_PRIORITY = {
    "run_next_experiment": 0,
    "run_limitation": 1,
    "doc_gap": 2,
    "todo_comment": 3,
}
_MAX_FILE_BYTES = 1_000_000


def discover_objectives(
    repo_path: str | Path,
    *,
    limit: int = 5,
    max_files: int = 4000,
) -> list[dict[str, Any]]:
    """Mine a repository for candidate research objectives.

    Signals, strongest first: prior-run research overviews (next experiments,
    then limitations), gap language in markdown docs, and TODO-style comments
    in source code. Candidates are deduplicated on normalized signal text.
    """
    repo = Path(repo_path)
    candidates: list[dict[str, Any]] = []
    candidates.extend(_mine_run_states(repo))
    candidates.extend(_mine_repo_files(repo, max_files=max_files))
    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = _normalize(candidate["signal"])
        if key and key not in deduped:
            deduped[key] = candidate
    ranked = sorted(
        deduped.values(),
        key=lambda candidate: (_KIND_PRIORITY[candidate["source_kind"]], candidate["source"]),
    )
    return ranked[: max(limit, 0)]


def _mine_run_states(repo: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for state_path in sorted(repo.glob("runs/*/state.json")):
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        overview = data.get("research_overview")
        if not isinstance(overview, dict):
            continue
        relative = state_path.relative_to(repo).as_posix()
        for text in _string_items(overview.get("next_experiments")):
            candidates.append(
                _candidate(
                    objective=f"Find testable ideas to advance the experiment: {text}",
                    source_kind="run_next_experiment",
                    source=f"{relative}:next_experiments",
                    signal=text,
                )
            )
        for text in _string_items(overview.get("limitations")):
            candidates.append(
                _candidate(
                    objective=f"Find testable ideas to address the limitation: {text}",
                    source_kind="run_limitation",
                    source=f"{relative}:limitations",
                    signal=text,
                )
            )
    return candidates


def _mine_repo_files(repo: Path, *, max_files: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(repo.rglob("*")):
        if scanned >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(repo).parts):
            continue
        suffix = path.suffix.lower()
        if suffix != ".md" and suffix not in _CODE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        relative = path.relative_to(repo).as_posix()
        if suffix == ".md":
            candidates.extend(_mine_doc_gaps(text, relative))
        else:
            candidates.extend(_mine_todo_comments(text, relative))
    return candidates


def _mine_doc_gaps(text: str, relative: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if any(term in lowered for term in _DOC_GAP_TERMS):
            signal = line.strip().lstrip("-*# ").strip()
            if signal:
                candidates.append(
                    _candidate(
                        objective=f"Find testable ideas to close the documented gap: {signal}",
                        source_kind="doc_gap",
                        source=f"{relative}:{line_number}",
                        signal=signal,
                    )
                )
    return candidates


def _mine_todo_comments(text: str, relative: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _TODO_PATTERN.search(line)
        if not match:
            continue
        signal = match.group(1).strip().rstrip("*/-> ").strip()
        if signal:
            candidates.append(
                _candidate(
                    objective=f"Find testable ideas to resolve: {signal}",
                    source_kind="todo_comment",
                    source=f"{relative}:{line_number}",
                    signal=signal,
                )
            )
    return candidates


def _candidate(*, objective: str, source_kind: str, source: str, signal: str) -> dict[str, Any]:
    return {
        "objective": objective,
        "source_kind": source_kind,
        "source": source,
        "signal": signal,
    }


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
