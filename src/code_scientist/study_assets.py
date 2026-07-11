from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_scientist.baselines import run_baseline_research
from code_scientist.evaluation import (
    build_capability_review_packet,
    build_feedback_loop_review_packet,
    build_preference_review_packet,
)
from code_scientist.models import Hypothesis, RunState


def write_paper_study_kit(out_dir: str | Path) -> list[Path]:
    output = Path(out_dir)
    benchmarks_dir = output / "benchmarks"
    review_dir = output / "review"
    validation_dir = output / "validation"
    benchmarks_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    benchmark_files = {
        "failure-replay-suite.json": _failure_replay_suite(),
        "review-grounding-suite.json": _review_grounding_suite(),
        "feedback-scaling-suite.json": _feedback_scaling_suite(),
    }
    for filename, payload in benchmark_files.items():
        files.append(_write_json(benchmarks_dir / filename, payload))

    files.append(_write_json(output / "study-manifest.json", _study_manifest()))
    files.append(_write_json(output / "ablation-manifest.json", _ablation_manifest()))
    files.append(_write_json(review_dir / "capability-review-spec.json", _capability_review_spec()))
    files.append(_write_json(review_dir / "preference-review-spec.json", _preference_review_spec()))
    files.append(_write_json(review_dir / "feedback-loop-review-spec.json", _feedback_loop_review_spec()))
    files.append(_write_json(validation_dir / "prospective-validation-template.json", _prospective_template()))
    files.append(_write_text(output / "README.md", _readme()))
    return files


def write_paper_study_materials(
    study_run_dir: str | Path,
    out_dir: str | Path,
    *,
    seed: str = "",
) -> list[Path]:
    states = _load_study_run_states(study_run_dir)
    if not states:
        raise ValueError(f"No study run states found under {study_run_dir}.")

    output = Path(out_dir)
    review_dir = output / "review"
    validation_dir = output / "validation"
    review_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    capability_spec = _capability_materials_spec(states)
    files.append(_write_json(review_dir / "capability-review-spec.json", capability_spec))
    capability_packet, capability_answer_key, capability_score_template = build_capability_review_packet(
        capability_spec,
        seed=seed,
    )
    files.append(_write_json(review_dir / "capability-review-packet.json", capability_packet))
    files.append(_write_json(review_dir / "capability-review-answer-key.json", capability_answer_key))
    files.append(_write_json(review_dir / "capability-review-score-template.json", capability_score_template))

    preference_spec = _preference_materials_spec(capability_spec)
    files.append(_write_json(review_dir / "preference-review-spec.json", preference_spec))
    preference_packet, preference_answer_key, preference_score_template = build_preference_review_packet(
        preference_spec,
        seed=seed,
    )
    files.append(_write_json(review_dir / "preference-review-packet.json", preference_packet))
    files.append(_write_json(review_dir / "preference-review-answer-key.json", preference_answer_key))
    files.append(_write_json(review_dir / "preference-review-template.json", preference_score_template))

    feedback_spec = _feedback_loop_materials_spec(states)
    files.append(_write_json(review_dir / "feedback-loop-review-spec.json", feedback_spec))
    feedback_packet, feedback_answer_key, feedback_score_template = build_feedback_loop_review_packet(
        feedback_spec,
        seed=seed,
    )
    files.append(_write_json(review_dir / "review-packet.json", feedback_packet))
    files.append(_write_json(review_dir / "answer-key.json", feedback_answer_key))
    files.append(_write_json(review_dir / "score-template.json", feedback_score_template))

    for state_path, state in states:
        top = _top_hypothesis(state)
        if top is None:
            continue
        files.append(
            _write_json(
                validation_dir / f"{_study_state_id(state_path)}-prospective-template.json",
                _prospective_template_for_hypothesis(top, state_path),
            )
        )
    files.append(_write_text(output / "README.md", _materials_readme()))
    return files


def _study_manifest() -> dict[str, Any]:
    return {
        "name": "Paper-style local coding-agent capability study",
        "description": (
            "A reproducible local starter study for exercising paper-level evaluation "
            "requirements before collecting real human or external measurements."
        ),
        "goals": [
            {
                "id": "failure-replay-small",
                "objective": (
                    "Find testable coding-agent workflow improvements that use retrieved "
                    "evidence and benchmark failure replay to reduce regressions."
                ),
                "cycles": 1,
                "max_hypotheses": 6,
                "max_matches": 4,
                "benchmark_suites": ["benchmarks/failure-replay-suite.json"],
                "auto_capability_eval": True,
                "baseline_name": "single_shot_llm",
                "baseline_score": 0.35,
                "scaling_label": "failure-replay-small",
                "scaling_baseline_score": 0.35,
                "tool_budget": 10,
                "safety_red_team": True,
            },
            {
                "id": "review-grounding-small",
                "objective": (
                    "Find coding-agent hypotheses that improve critic-before-edit review, "
                    "assumption decomposition, and contradiction-aware memory."
                ),
                "cycles": 2,
                "max_hypotheses": 8,
                "max_matches": 5,
                "benchmark_suites": ["benchmarks/review-grounding-suite.json"],
                "auto_capability_eval": True,
                "baseline_name": "single_shot_llm",
                "baseline_score": 0.37,
                "scaling_label": "review-grounding-small",
                "scaling_baseline_score": 0.37,
                "tool_budget": 13,
                "safety_red_team": True,
            },
            {
                "id": "feedback-scaling-small",
                "objective": (
                    "Find ways to make meta-review feedback, tournament ranking, and "
                    "tool-use scheduling improve coding-agent research quality over cycles."
                ),
                "cycles": 3,
                "max_hypotheses": 10,
                "max_matches": 6,
                "benchmark_suites": ["benchmarks/feedback-scaling-suite.json"],
                "auto_capability_eval": True,
                "baseline_name": "single_shot_llm",
                "baseline_score": 0.39,
                "scaling_label": "feedback-scaling-small",
                "scaling_baseline_score": 0.39,
                "tool_budget": 16,
                "safety_red_team": True,
            },
        ],
    }


def _ablation_manifest() -> dict[str, Any]:
    objective = (
        "Find coding-agent hypotheses that improve critic-before-edit review, assumption "
        "decomposition, retrieval grounding, and benchmark reliability."
    )
    common: dict[str, Any] = {
        "objective": objective,
        "cycles": 1,
        "max_hypotheses": 6,
        "max_matches": 4,
        "benchmark_suites": ["benchmarks/review-grounding-suite.json"],
        "auto_capability_eval": True,
        "baseline_name": "single_shot_llm",
        "baseline_score": 0.37,
        "scaling_baseline_score": 0.37,
        "tool_budget": 8,
    }
    arms = [
        ("generation-paper-seeded", {"generation_methods": ["paper_seeded_idea_generation"]}),
        ("generation-assumption", {"generation_methods": ["assumption_decomposition"]}),
        ("reflection-search-off", {"review_types": ["initial_review", "safety_review"]}),
        (
            "reflection-search-on",
            {"review_types": ["full_review", "deep_verification", "observation_review"]},
        ),
        ("ranking-simple", {"review_types": ["initial_review", "single_turn_debate"]}),
        ("ranking-debate", {"generation_methods": ["simulated_debate"]}),
        ("evolution-off", {"disabled_agents": ["evolution"]}),
        ("evolution-on", {}),
        ("review-full", {"review_types": ["full_review", "deep_verification"]}),
        ("review-recurrent", {"review_types": ["recurrent_tournament_review"]}),
        ("proximity-off", {"disabled_agents": ["proximity"]}),
        ("proximity-on", {}),
    ]
    return {
        "name": "Code Scientist v2 component ablation study",
        "description": (
            "Paired runnable arms for generation strategy, reflection search, simple versus "
            "debate ranking, evolution, full versus recurrent review, and proximity controls."
        ),
        "goals": [
            {
                **common,
                "id": arm_id,
                "scaling_label": arm_id,
                **overrides,
            }
            for arm_id, overrides in arms
        ],
    }


def _load_study_run_states(study_run_dir: str | Path) -> list[tuple[Path, RunState]]:
    root = Path(study_run_dir)
    states: list[tuple[Path, RunState]] = []
    for path in sorted(root.glob("*/state.json")):
        states.append((path, RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))))
    return states


def _capability_materials_spec(states: list[tuple[Path, RunState]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    refs: list[str] = []
    objectives: list[str] = []
    for state_path, state in states:
        top = _top_hypothesis(state)
        if top is None:
            continue
        baseline = run_baseline_research(state.goal.objective).hypotheses[0]
        refs.append(str(state_path))
        objectives.append(state.goal.objective)
        items.append(
            {
                "item_id": top.id,
                "hypothesis_id": top.id,
                "prompt": "Score which anonymous arm better satisfies the study objective and rubric.",
                "baseline_artifact": _hypothesis_artifact(baseline, role="single_shot_baseline"),
                "code_scientist_artifact": _hypothesis_artifact(top, role="code_scientist_candidate"),
            }
        )
    if not items:
        raise ValueError("Study run states do not contain hypotheses for review materials.")
    return {
        "goal_id": "paper-study-human-review",
        "objective": "Score Code Scientist outputs against deterministic single-shot baselines.",
        "baseline_name": "single_shot_llm",
        "artifact_refs": refs,
        "metrics": ["novelty", "plausibility", "impact", "testability", "safety"],
        "instructions": (
            "Score each anonymous arm without using the private answer key. "
            "Use the same rubric for all study goals."
        ),
        "review_items": items,
        "study_objectives": objectives,
    }


def _feedback_loop_materials_spec(states: list[tuple[Path, RunState]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    refs: list[str] = []
    source_meta_review_ids: list[str] = []
    for state_path, state in states:
        top = _top_hypothesis(state)
        if top is None:
            continue
        baseline = run_baseline_research(state.goal.objective).hypotheses[0]
        refs.append(str(state_path))
        if state.meta_reviews:
            source_meta_review_ids.append(state.meta_reviews[-1].id)
        item = {
            "item_id": top.id,
            "prompt": (
                "Score whether the observed arm is a better research output after the "
                "Code Scientist loop than the baseline arm."
            ),
            "baseline_artifact": _hypothesis_artifact(baseline, role="single_shot_before_loop"),
            "observed_artifact": {
                **_hypothesis_artifact(top, role="code_scientist_after_loop"),
                "meta_review_context": [_meta_review_artifact(review) for review in state.meta_reviews[-2:]],
            },
        }
        items.append(item)
    if not items:
        raise ValueError("Study run states do not contain hypotheses for feedback-loop review materials.")
    return {
        "cycle": 1,
        "source_meta_review_id": source_meta_review_ids[-1] if source_meta_review_ids else "paper-study-materials",
        "feedback_agents": ["generation", "reflection", "ranking", "meta_review"],
        "feedback_item_count": len(items),
        "adopted_feedback_count": 0,
        "measurement_source": "external_blind_review",
        "artifact_refs": refs,
        "metrics": ["quality", "specificity", "testability"],
        "instructions": (
            "Score each anonymous before/after arm without using the private answer key. "
            "The private key is only for ingestion after reviewers return scores."
        ),
        "review_items": items,
    }


def _preference_materials_spec(capability_spec: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in capability_spec.get("review_items", []):
        if not isinstance(item, dict):
            continue
        preference_item = {key: value for key, value in item.items() if key != "prompt"}
        preference_item["prompt"] = (
            "Choose which anonymous arm is the stronger research output for the study objective."
        )
        items.append(preference_item)
    if not items:
        raise ValueError("Capability review spec does not contain items for preference review.")
    return {
        "goal_id": "paper-study-human-preference",
        "objective": "Choose Code Scientist outputs or single-shot baselines by blind human preference.",
        "baseline_name": capability_spec.get("baseline_name", "single_shot_llm"),
        "artifact_refs": capability_spec.get("artifact_refs", []),
        "instructions": (
            "Choose the anonymous arm you would prefer to carry forward for implementation "
            "or external validation. Use no_preference only when the arms are equivalent."
        ),
        "review_items": items,
        "study_objectives": capability_spec.get("study_objectives", []),
    }


def _top_hypothesis(state: RunState) -> Hypothesis | None:
    if not state.hypotheses:
        return None
    top_ids = [
        evaluation.top_hypothesis_id
        for evaluation in state.capability_evaluations
        if evaluation.top_hypothesis_id
    ]
    for hypothesis_id in top_ids:
        for hypothesis in state.hypotheses:
            if hypothesis.id == hypothesis_id:
                return hypothesis
    return max(state.hypotheses, key=lambda hypothesis: hypothesis.elo)


def _hypothesis_artifact(hypothesis: Hypothesis, *, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "hypothesis_id": hypothesis.id,
        "title": hypothesis.title,
        "claim": hypothesis.claim,
        "rationale": hypothesis.rationale,
        "assumptions": hypothesis.assumptions,
        "test_plan": hypothesis.test_plan.to_dict(),
        "risks": hypothesis.risks,
        "origin": hypothesis.origin,
        "parent_ids": hypothesis.parent_ids,
        "generation_trace": hypothesis.generation_trace,
        "evolution_trace": hypothesis.evolution_trace,
        "elo": round(hypothesis.elo, 3),
        "status": hypothesis.status,
    }


def _meta_review_artifact(review) -> dict[str, Any]:
    return {
        "id": review.id,
        "common_weaknesses": review.common_weaknesses,
        "safety_concerns": review.safety_concerns,
        "missing_evidence": review.missing_evidence,
        "promising_directions": review.promising_directions,
        "prompt_feedback": review.prompt_feedback,
        "agent_feedback": review.agent_feedback,
        "evidence_refs": review.evidence_refs,
    }


def _prospective_template_for_hypothesis(hypothesis: Hypothesis, state_path: Path) -> dict[str, Any]:
    payload = _prospective_template()
    payload["hypothesis_id"] = hypothesis.id
    payload["source_state"] = str(state_path)
    payload["notes"] = [
        f"Fill measured metrics after implementing or externally validating {hypothesis.id}.",
    ]
    return payload


def _study_state_id(state_path: Path) -> str:
    return state_path.parent.name.replace("/", "-").replace(" ", "-")


def _failure_replay_suite() -> dict[str, Any]:
    return {
        "name": "Paper-style failure replay benchmark",
        "baseline": _baseline_metrics(),
        "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
        "cases": [
            {
                "id": "failure-derived-seeds",
                "required_terms": ["failure-derived benchmark seeds", "regression"],
            },
            {
                "id": "retrieved-evidence-loop",
                "required_terms": ["retrieved evidence", "pass_rate"],
            },
            {
                "id": "local-measurement-boundary",
                "required_terms": ["benchmark", "without unacceptable cost"],
            },
        ],
    }


def _review_grounding_suite() -> dict[str, Any]:
    return {
        "name": "Paper-style review grounding benchmark",
        "baseline": _baseline_metrics(),
        "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
        "cases": [
            {
                "id": "critic-before-edit",
                "required_terms": ["critic-before-edit", "assumption"],
            },
            {
                "id": "contradiction-memory",
                "required_terms": ["memory", "contradictions"],
            },
            {
                "id": "tournament-ranking",
                "required_terms": ["pairwise tournament", "prompt variants"],
            },
        ],
    }


def _feedback_scaling_suite() -> dict[str, Any]:
    return {
        "name": "Paper-style feedback and scaling benchmark",
        "baseline": _baseline_metrics(),
        "case_cost": {"tool_calls": 2, "wall_time": 1.5, "cost": 0.03},
        "cases": [
            {
                "id": "meta-review-feedback",
                "required_terms": ["meta-review", "prompt feedback"],
            },
            {
                "id": "tool-budget-scheduler",
                "required_terms": ["tool-use budget", "pass rate"],
            },
            {
                "id": "feedback-loop-measurement",
                "required_terms": ["review critiques", "later generations"],
            },
        ],
    }


def _baseline_metrics() -> dict[str, float]:
    return {
        "pass_rate": 0.0,
        "regression_count": 3.0,
        "tool_calls": 0.0,
        "wall_time": 0.0,
        "cost": 0.0,
    }


def _capability_review_spec() -> dict[str, Any]:
    return {
        "goal_id": "paper-study-human-review",
        "objective": "Score Code Scientist outputs against single-shot baselines.",
        "baseline_name": "single_shot_llm",
        "metrics": ["novelty", "plausibility", "impact", "testability", "safety"],
        "review_items": [
            {
                "item_id": "replace-with-hypothesis-id",
                "baseline_artifact": {
                    "title": "Paste or link the baseline arm output here.",
                    "claim": "Replace after running the study.",
                },
                "code_scientist_artifact": {
                    "hypothesis_id": "replace-with-hypothesis-id",
                    "title": "Paste or link the Code Scientist arm output here.",
                    "claim": "Replace after running the study.",
                },
            }
        ],
    }


def _preference_review_spec() -> dict[str, Any]:
    return {
        "goal_id": "paper-study-human-preference",
        "objective": "Choose Code Scientist outputs or single-shot baselines by blind human preference.",
        "baseline_name": "single_shot_llm",
        "review_items": [
            {
                "item_id": "replace-with-hypothesis-id",
                "baseline_artifact": {
                    "title": "Paste or link the baseline arm output here.",
                    "claim": "Replace after running the study.",
                },
                "code_scientist_artifact": {
                    "hypothesis_id": "replace-with-hypothesis-id",
                    "title": "Paste or link the Code Scientist arm output here.",
                    "claim": "Replace after running the study.",
                },
            }
        ],
    }


def _feedback_loop_review_spec() -> dict[str, Any]:
    return {
        "cycle": 2,
        "source_meta_review_id": "replace-with-meta-review-id",
        "feedback_agents": ["generation", "reflection", "ranking"],
        "feedback_item_count": 3,
        "adopted_feedback_count": 1,
        "measurement_source": "external_blind_review",
        "metrics": ["quality", "specificity", "testability"],
        "review_items": [
            {
                "item_id": "replace-with-feedback-item-id",
                "baseline_artifact": {
                    "summary": "Paste an output before meta-review feedback was applied.",
                },
                "observed_artifact": {
                    "summary": "Paste the matched output after feedback was applied.",
                },
            }
        ],
    }


def _prospective_template() -> dict[str, Any]:
    return {
        "hypothesis_id": "replace-with-selected-hypothesis-id",
        "implementation_refs": ["replace-with-commit-or-run-artifact"],
        "baseline_metrics": {
            "pass_rate": 0.0,
            "regression_count": 0.0,
            "tool_calls": 0.0,
            "wall_time": 0.0,
            "cost": 0.0,
        },
        "measured_metrics": {
            "pass_rate": 0.0,
            "regression_count": 0.0,
            "tool_calls": 0.0,
            "wall_time": 0.0,
            "cost": 0.0,
        },
        "success_metric": "pass_rate",
        "measurement_source": "replace-with-validation-source",
        "measurement_status": "measured",
        "notes": [
            "Replace placeholder values after implementing or externally measuring a selected hypothesis.",
        ],
    }


def _readme() -> str:
    return """# Paper-Style Local Study Kit

This kit is a local starter study for moving Code Scientist from paper-shaped
infrastructure toward paper-style evidence. It does not replace human review or
external validation; it gives those workflows concrete artifacts to run and fill.

Run the local study:

```bash
uv run code-scientist study-run study-manifest.json --out runs/paper-study-local
```

Run the paired component-ablation arms:

```bash
uv run code-scientist study-run ablation-manifest.json --out runs/paper-ablation-local
```

The ablation manifest exercises generation strategy, reflection search,
simple versus debate ranking, evolution on/off, full versus recurrent review,
and proximity on/off through explicit plan overrides and disabled-agent arms.

Then aggregate the generated run states:

```bash
uv run code-scientist study runs/paper-study-local/*/state.json --out runs/paper-study-local/study-audit.md
```

Build populated reviewer and validation materials from the completed run:

```bash
uv run code-scientist paper-study-materials runs/paper-study-local --out runs/paper-study-local/materials --seed paper-study
```

Use `review/capability-review-spec.json` with
`code-scientist capability-review-packet` after replacing placeholder artifacts
with real baseline and Code Scientist outputs. Use
`review/preference-review-spec.json` with
`code-scientist preference-review-packet` when reviewers should make a blind
winner/no-preference choice instead of rubric scores. Use
`review/feedback-loop-review-spec.json` with
`code-scientist feedback-loop-review-packet` after selecting before/after
feedback-loop artifacts. Use
`validation/prospective-validation-template.json` as the shape for measured
implementation outcomes. Replace `measurement_source` with the held-out suite,
blind review, or deployment artifact that produced the numbers, or add a
no-shell command-list `command` field and run
`code-scientist prospective-validation-run` to produce the measured fixture.
Study-run manifests can also include per-goal
`prospective_validation_manifests` when the validation command should run as
part of the multi-goal study.
"""


def _materials_readme() -> str:
    return """# Paper-Style Study Review Materials

These files are populated from completed `code-scientist study-run` states.

Send the public review packets to reviewers:

```bash
review/capability-review-packet.json
review/preference-review-packet.json
review/review-packet.json
```

Keep the answer keys private until scores are returned:

```bash
review/capability-review-answer-key.json
review/preference-review-answer-key.json
review/answer-key.json
```

After reviewers fill the score templates, combine each returned score file with
its private answer key and ingest them with:

```bash
uv run code-scientist capability-review-fixture review/capability-review-score-template.json \
  --answer-key review/capability-review-answer-key.json \
  --out returned-capability-scores.json \
  --human-rubric-scale 5
uv run code-scientist feedback-loop-review-fixture review/score-template.json \
  --answer-key review/answer-key.json \
  --out returned-feedback-scores.json
uv run code-scientist preference-review-fixture review/preference-review-template.json \
  --answer-key review/preference-review-answer-key.json \
  --out returned-preference-scores.json
uv run code-scientist study-run study-manifest.json \
  --capability-review-fixture returned-capability-scores.json \
  --preference-review-fixture returned-preference-scores.json \
  --feedback-loop-review-fixture returned-feedback-scores.json \
  --out runs/paper-study-reviewed
```

Use the files in `validation/` as per-hypothesis prospective validation fixture
templates after implementing or externally measuring selected hypotheses. For
repeatable validation harnesses, add a command-list `command` to a validation
manifest and either reference it from a goal's `prospective_validation_manifests`
list or run it directly:

```bash
uv run code-scientist prospective-validation-run path/to/state.json validation/example-prospective-template.json \
  --work-dir runs/paper-study-local/prospective-work \
  --out returned-prospective-validation.json
```
"""


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
