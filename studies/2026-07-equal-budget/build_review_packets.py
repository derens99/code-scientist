"""Build independently randomized blinded packets and a private answer key."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


def _code_scientist_candidate(root: Path, goal: str) -> dict[str, Any]:
    state = _load(root / "code-scientist" / goal / "state.json")
    hypotheses = state.get("hypotheses", [])
    top = max(hypotheses, key=lambda item: (float(item.get("elo", 0.0)), str(item["id"])))
    return {
        "title": top.get("title", ""),
        "intervention_and_claim": top.get("claim", ""),
        "rationale_or_mechanism": top.get("rationale", ""),
        "assumptions": top.get("assumptions", []),
        "risks": top.get("risks", []),
        "test_plan": top.get("test_plan", {}),
    }


def _baseline_candidate(root: Path, goal: str) -> dict[str, Any]:
    result = _load(root / "baseline" / goal / "result.json")
    proposal = result["selected"]["proposal"]
    return {
        "title": proposal.get("title", ""),
        "intervention_and_claim": " ".join(
            value
            for value in (proposal.get("intervention", ""), proposal.get("claim", ""))
            if value
        ),
        "rationale_or_mechanism": proposal.get("mechanism", ""),
        "assumptions": proposal.get("assumptions", []),
        "risks": proposal.get("risks", []),
        "test_plan": proposal.get("test_plan", {}),
    }


def _swap(reviewer: int, goal: str, seed: str) -> bool:
    digest = hashlib.sha256(f"{seed}:{reviewer}:{goal}".encode()).digest()
    return bool(digest[0] & 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--seed", default="equal-budget-20260712")
    args = parser.parse_args()
    artifacts = Path(args.artifacts)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    answer_key: dict[str, dict[str, str]] = {}

    for reviewer in range(1, 4):
        items = []
        reviewer_key: dict[str, str] = {}
        for goal in GOALS:
            candidates = {
                "code_scientist": _code_scientist_candidate(artifacts, goal),
                "single_shot_baseline": _baseline_candidate(artifacts, goal),
            }
            if _swap(reviewer, goal, args.seed):
                labels = {"arm_a": "single_shot_baseline", "arm_b": "code_scientist"}
            else:
                labels = {"arm_a": "code_scientist", "arm_b": "single_shot_baseline"}
            reviewer_key[goal] = labels["arm_b"]
            items.append(
                {
                    "item_id": goal,
                    "objective": _load(Path(__file__).with_name("study-manifest.json"))["goals"][
                        GOALS.index(goal)
                    ]["objective"],
                    "arm_a": candidates[labels["arm_a"]],
                    "arm_b": candidates[labels["arm_b"]],
                }
            )
        packet = {
            "reviewer_id": f"reviewer-{reviewer}",
            "blinding": "Arm labels are independently randomized. No engine traces or outcomes are included.",
            "instructions": (
                "For each item, choose arm_a, arm_b, or no_preference. Score each arm from 1 to 5 "
                "on every rubric field. Judge only objective fit and proposal quality; do not infer provenance."
            ),
            "rubric": list(RUBRIC),
            "items": items,
            "return_schema": {
                "reviewer_id": f"reviewer-{reviewer}",
                "reviews": [
                    {
                        "item_id": "goal id",
                        "preferred_arm": "arm_a|arm_b|no_preference",
                        "arm_a_scores": {field: "integer 1..5" for field in RUBRIC},
                        "arm_b_scores": {field: "integer 1..5" for field in RUBRIC},
                        "justification": "short reason",
                        "confidence": "number 0..1",
                    }
                ],
            },
        }
        packet_path = output / f"reviewer-{reviewer}-packet.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        answer_key[f"reviewer-{reviewer}"] = reviewer_key

    Path(args.private_key).write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
