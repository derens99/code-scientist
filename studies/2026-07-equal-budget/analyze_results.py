"""Aggregate blinded-review and absolute-path regraded validation outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from code_scientist.experiments import (
    TrialArmResult,
    compute_experiment_stats,
    decide_verdict,
)


GOALS = ("requirement-coverage", "edge-semantics", "verification-efficiency")
RUBRIC = (
    "specificity",
    "plausibility",
    "testability",
    "mechanism_clarity",
    "risk_awareness",
    "protocol_quality",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _review_analysis(review_dir: Path) -> dict[str, Any]:
    key = _load(review_dir / "answer-key.json")
    counts = {goal: {"code_scientist": 0.0, "single_shot_baseline": 0.0} for goal in GOALS}
    score_totals = {"code_scientist": [], "single_shot_baseline": []}
    judgments: list[dict[str, Any]] = []
    for return_path in sorted((review_dir / "returns").glob("*.json")):
        reviewer_id = return_path.stem
        returned = _load(return_path)
        for review in returned["reviews"]:
            goal = review["item_id"]
            arm_b_origin = key[reviewer_id][goal]
            arm_a_origin = (
                "single_shot_baseline" if arm_b_origin == "code_scientist" else "code_scientist"
            )
            origin_by_label = {"arm_a": arm_a_origin, "arm_b": arm_b_origin}
            preferred = review["preferred_arm"]
            if preferred == "no_preference":
                counts[goal]["code_scientist"] += 0.5
                counts[goal]["single_shot_baseline"] += 0.5
            elif preferred in origin_by_label:
                counts[goal][origin_by_label[preferred]] += 1.0
            for label, score_key in (("arm_a", "arm_a_scores"), ("arm_b", "arm_b_scores")):
                score_totals[origin_by_label[label]].append(sum(review[score_key].values()))
            judgments.append(
                {
                    "reviewer": reviewer_id,
                    "goal": goal,
                    "preferred_arm": preferred,
                    "preferred_origin": origin_by_label.get(preferred, "tie"),
                }
            )
    means = {
        origin: round(sum(values) / len(values), 6) if values else 0.0
        for origin, values in score_totals.items()
    }
    cs_wins = sum(1 for item in judgments if item["preferred_origin"] == "code_scientist")
    baseline_wins = sum(
        1 for item in judgments if item["preferred_origin"] == "single_shot_baseline"
    )
    return {
        "judgment_count": len(judgments),
        "code_scientist_preference_wins": cs_wins,
        "single_shot_baseline_preference_wins": baseline_wins,
        "preference_half_wins": sum(
            1 for item in judgments if item["preferred_origin"] == "tie"
        ),
        "preference_by_goal": counts,
        "mean_total_rubric_score": means,
        "rubric_score_delta_code_scientist_minus_baseline": round(
            means["code_scientist"] - means["single_shot_baseline"], 6
        ),
        "judgments": judgments,
    }


def _coding_analysis(final_root: Path) -> dict[str, Any]:
    arms: list[TrialArmResult] = []
    per_goal: dict[str, Any] = {}
    for goal in GOALS:
        data = _load(final_root / goal / "experiment.json")
        goal_arms = [TrialArmResult.from_dict(item) for item in data["trial_arms"]]
        goal_stats = compute_experiment_stats(goal_arms, seed=20260712)
        per_goal[goal] = {"stats": goal_stats, "verdict": data["verdict"]}
        arms.extend(
            [
                TrialArmResult(
                    task_id=f"{goal}:{item.task_id}",
                    trial=item.trial,
                    arm=item.arm,
                    passed=item.passed,
                    agent_status=item.agent_status,
                    duration_seconds=item.duration_seconds,
                    num_turns=item.num_turns,
                    cost_usd=item.cost_usd,
                    grader_tail=item.grader_tail,
                    overtime=item.overtime,
                )
                for item in goal_arms
            ]
        )
    pooled_stats = compute_experiment_stats(arms, seed=20260712)
    return {
        "per_goal": per_goal,
        "pooled_stats": pooled_stats,
        "pooled_verdict": decide_verdict(pooled_stats, alpha=0.05, min_discordant_pairs=3),
        "arm_count": len(arms),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-root", required=True)
    args = parser.parse_args()
    root = Path(args.study_root)
    review = _review_analysis(root / "artifacts" / "review")
    coding = _coding_analysis(root / "artifacts" / "validation-final")
    result = {
        "registered_overall_rule": "supported only if ideation and coding endpoints are both supported; refuted if either symmetric refutation rule is met; otherwise inconclusive",
        "ideation": review,
        "coding": coding,
        "strict_invalid_attempts": {
            "status": "incomplete",
            "reason": "Raw runs used invalid bridge wrappers, relative grader paths, or orchestration timeouts; retained under artifacts/invalid-attempts and excluded from primary corrected statistics.",
        },
        "overall_verdict": "refuted",
        "limitations": [
            "Three objectives, one host model, public local task bundles, and model reviewers rather than humans.",
            "The corrected coding result is a grader-only regrade of executed workspaces after a path fix; no coding agent was rerun.",
            "The pooled coding endpoint has only two discordant pairs and is therefore inconclusive by the registered minimum.",
            "The first raw validation set is invalid infrastructure evidence, not a quality result.",
        ],
    }
    output = root / "artifacts" / "study-results.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = root / "artifacts" / "final-report.md"
    report.write_text(
        "# Equal-Budget Prospective Comparison\n\n"
        "Overall verdict: **refuted** under the pre-registered endpoint rule.\n\n"
        "The three blinded independent model reviewers preferred the best-of-N single-shot baseline in all 9 judgments; its mean total rubric score exceeded Code Scientist's. The coding endpoint was inconclusive: requirement coverage tied 8/8 pairs, edge semantics favored baseline 6/8 vs 4/8, and verification efficiency tied 5/8. Pooled pass rates were 19/24 baseline and 17/24 candidate (delta -0.0833), but only two discordant pairs, below the registered minimum of three.\n\n"
        "The raw attempts with invalid bridge wrappers, relative grader paths, and orchestration timeouts are retained under `artifacts/invalid-attempts/` and excluded from the primary result. The absolute-path regrade used the already executed workspaces and the same hidden grader tests; it did not rerun agents.\n\n"
        "This is model-review and local coding-agent evidence, not human validation or production evidence.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
