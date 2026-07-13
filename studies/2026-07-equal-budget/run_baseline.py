"""Run the pre-registered matched-call best-of-N single-shot baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from code_scientist.llm import HostAgentBridgeClient, LLMResponseError


RUBRIC = (
    "specificity, plausibility, testability, mechanism clarity, risk awareness, "
    "and protocol quality"
)


def _json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError("Baseline host response did not contain a JSON object.")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise LLMResponseError("Baseline host response must be a JSON object.")
    return value


def _digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _proposal_prompt(objective: str, ordinal: int) -> str:
    return f"""You are the model in a pre-registered best-of-N single-shot baseline.
Independently answer the objective below in one pass. You have not seen and must not assume
any other candidate. Produce exactly one appended system-prompt intervention, not a workflow.

Objective: {objective}

Return only JSON:
{{"title":"...","intervention":"one imperative instruction","claim":"A/B-testable claim",
"mechanism":"causal explanation","assumptions":["..."],"risks":["..."],
"test_plan":{{"experiment":"...","metrics":["pass_rate","wall_time","turns"],
"success_condition":"..."}},"single_shot_ordinal":{ordinal}}}
Do not claim measured improvement. Keep the intervention bounded and auditable."""


def _selection_prompt(objective: str, proposals: list[dict[str, Any]]) -> str:
    anonymous = [
        {
            "candidate_id": proposal["candidate_id"],
            **{
                key: value
                for key, value in proposal["proposal"].items()
                if key != "single_shot_ordinal"
            },
        }
        for proposal in proposals
    ]
    return f"""Select the strongest single-shot proposal for this objective:
{objective}

Score only {RUBRIC}. Do not combine or rewrite candidates. Candidate order is randomized data.
Candidates:
{json.dumps(anonymous, ensure_ascii=False)}

Return only JSON: {{"selected_id":"...","reason":"...","scores":{{"specificity":1,
"plausibility":1,"testability":1,"mechanism_clarity":1,"risk_awareness":1,
"protocol_quality":1}}}}. Every score must be an integer from 1 to 5."""


def run_goal(goal: dict[str, Any], calls: int, output: Path) -> None:
    if calls < 8:
        raise ValueError(f"{goal['id']}: realized Code Scientist call count {calls} is below 8")
    selectors = max(2, calls // 4)
    proposal_count = calls - selectors
    bridge = HostAgentBridgeClient(output / "llm-bridge")
    proposals: list[dict[str, Any]] = []
    for ordinal in range(1, proposal_count + 1):
        proposal = _json_object(
            bridge.complete(_proposal_prompt(str(goal["objective"]), ordinal), max_tokens=4096)
        )
        proposal_digest = _digest(proposal)
        candidate_id = f"candidate-{proposal_digest}-{ordinal:02d}"
        proposals.append(
            {
                "candidate_id": candidate_id,
                "proposal_digest": proposal_digest,
                "proposal": proposal,
            }
        )

    ordered = sorted(proposals, key=lambda item: str(item["candidate_id"]))
    selections: list[dict[str, Any]] = []
    for selector in range(selectors):
        rotated = ordered[selector % len(ordered) :] + ordered[: selector % len(ordered)]
        selection = _json_object(
            bridge.complete(
                _selection_prompt(str(goal["objective"]), rotated), max_tokens=4096
            )
        )
        selected_id = str(selection.get("selected_id", ""))
        if selected_id not in {item["candidate_id"] for item in proposals}:
            raise LLMResponseError(f"Selector returned unknown candidate id: {selected_id}")
        selections.append(selection)

    votes = Counter(str(item["selected_id"]) for item in selections)
    digest_by_id = {
        str(item["candidate_id"]): (str(item["proposal_digest"]), str(item["candidate_id"]))
        for item in proposals
    }
    winner_id = min(
        votes,
        key=lambda candidate_id: (-votes[candidate_id], *digest_by_id[candidate_id]),
    )
    winner = next(item for item in proposals if item["candidate_id"] == winner_id)
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(
        json.dumps(
            {
                "goal": goal,
                "matched_call_count": calls,
                "proposal_call_count": proposal_count,
                "selection_call_count": selectors,
                "proposals": proposals,
                "selections": selections,
                "selected": winner,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("call_counts", help="JSON object mapping goal id to realized calls")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    counts = json.loads(Path(args.call_counts).read_text(encoding="utf-8"))
    root = Path(args.out)
    for goal in manifest["goals"]:
        run_goal(goal, int(counts[goal["id"]]), root / goal["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
