import json
from pathlib import Path

from code_scientist.objective_discovery import discover_objectives


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "worker.py").write_text(
        "def run():\n"
        "    # TODO: retry transient tool failures instead of aborting the cycle\n"
        "    return None\n",
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "roadmap.md").write_text(
        "# Roadmap\n\nElo-versus-correctness concordance is not yet implemented.\n",
        encoding="utf-8",
    )
    run_dir = repo / "runs" / "prior-run"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "goal": {"objective": "Improve coding-agent review loops"},
                "research_overview": {
                    "next_experiments": ["Benchmark quarantine impact on tournament quality."],
                    "limitations": ["Needs prospective validation on an objective benchmark."],
                },
            }
        ),
        encoding="utf-8",
    )
    vendor = repo / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.js").write_text("// TODO: vendored noise\n", encoding="utf-8")
    return repo


def test_discover_objectives_mines_run_states_docs_and_todos(tmp_path):
    repo = _seed_repo(tmp_path)

    candidates = discover_objectives(repo, limit=10)

    kinds = [candidate["source_kind"] for candidate in candidates]
    assert "run_next_experiment" in kinds
    assert "run_limitation" in kinds
    assert "doc_gap" in kinds
    assert "todo_comment" in kinds
    assert kinds.index("run_next_experiment") < kinds.index("todo_comment")

    todo = next(candidate for candidate in candidates if candidate["source_kind"] == "todo_comment")
    assert "retry transient tool failures" in todo["objective"]
    assert todo["source"].endswith("worker.py:2")

    doc_gap = next(candidate for candidate in candidates if candidate["source_kind"] == "doc_gap")
    assert "concordance" in doc_gap["objective"].lower()

    assert all("vendored noise" not in candidate["objective"] for candidate in candidates)


def test_discover_objectives_dedupes_repeated_signals_and_applies_limit(tmp_path):
    repo = _seed_repo(tmp_path)
    (repo / "src" / "other.py").write_text(
        "# TODO: retry transient tool failures instead of aborting the cycle\n",
        encoding="utf-8",
    )

    unlimited = discover_objectives(repo, limit=10)
    todo_signals = [
        candidate["signal"]
        for candidate in unlimited
        if candidate["source_kind"] == "todo_comment"
    ]
    assert len(todo_signals) == 1, "repeated TODO text must collapse to one candidate"

    limited = discover_objectives(repo, limit=2)
    assert len(limited) == 2
    assert all(
        candidate["source_kind"] in {"run_next_experiment", "run_limitation"}
        for candidate in limited
    ), "the strongest signal kinds win under a tight limit"


def test_discover_objectives_handles_repo_without_signals(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "README.md").write_text("# Nothing to see\n", encoding="utf-8")

    assert discover_objectives(repo, limit=5) == []
