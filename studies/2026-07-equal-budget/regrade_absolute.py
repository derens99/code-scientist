"""Re-run hidden graders against already executed workspaces.

The first validation attempt used relative output paths, so the grader config
resolved under each workspace. This script preserves the agent workspaces and
metadata, copies them to absolute final artifact paths, and reruns only the
held-out grader. It does not rerun an agent or alter source files.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from code_scientist.experiments import (
    ExperimentProtocol,
    ExperimentResult,
    TrialArmResult,
    compute_experiment_stats,
    decide_verdict,
    grade_workspace,
    load_agent_tasks,
    render_experiment_report,
)


def regrade(goal: str, invalid_root: Path, final_root: Path, suite: Path) -> None:
    source_root = invalid_root / f"validation-relative-{goal}"
    final_root = final_root / goal
    protocol = ExperimentProtocol.from_dict(
        json.loads((source_root / "protocol.json").read_text(encoding="utf-8"))
    )
    prior = ExperimentResult.from_dict(
        json.loads((source_root / "experiment.json").read_text(encoding="utf-8"))
    )
    tasks = {task.id: task for task in load_agent_tasks(suite, protocol.task_ids)}
    final_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "protocol.json", final_root / "protocol.json")
    arms: list[TrialArmResult] = []
    for prior_arm in prior.trial_arms:
        arm_rel = Path("trials") / prior_arm.task_id / f"trial-{prior_arm.trial}" / prior_arm.arm
        source_arm = source_root / arm_rel
        target_arm = final_root / arm_rel
        target_arm.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_arm, target_arm, dirs_exist_ok=True)
        target_workspace = target_arm / "workspace"
        passed, grader_tail = grade_workspace(
            target_workspace,
            tasks[prior_arm.task_id].grader_dir(),
            timeout=120.0,
        )
        (target_arm / "grader-output.txt").write_text(grader_tail, encoding="utf-8")
        corrected = TrialArmResult(
            task_id=prior_arm.task_id,
            trial=prior_arm.trial,
            arm=prior_arm.arm,
            passed=passed and not prior_arm.overtime,
            agent_status=prior_arm.agent_status,
            duration_seconds=prior_arm.duration_seconds,
            num_turns=prior_arm.num_turns,
            cost_usd=prior_arm.cost_usd,
            grader_tail=grader_tail[-400:],
            overtime=prior_arm.overtime,
        )
        arms.append(corrected)

    stats = compute_experiment_stats(arms, seed=protocol.seed)
    verdict = decide_verdict(
        stats,
        alpha=protocol.alpha,
        min_discordant_pairs=protocol.min_discordant_pairs,
    )
    result = ExperimentResult(
        experiment_id=protocol.id,
        protocol_hash=protocol.content_hash(),
        status="complete",
        started_at=prior.started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        trial_arms=arms,
        stats=stats,
        verdict=verdict,
        total_cost_usd=prior.total_cost_usd,
        notes=[
            "Regraded from executed workspaces after relative grader-path infrastructure failure.",
            "No agent was rerun; absolute final artifact paths were used for this grader pass.",
        ],
    )
    (final_root / "experiment.json").write_text(
        json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    (final_root / "experiment-report.md").write_text(
        render_experiment_report(protocol, result), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", action="append", required=True)
    parser.add_argument("--invalid-root", required=True)
    parser.add_argument("--final-root", required=True)
    parser.add_argument("--suite", required=True)
    args = parser.parse_args()
    for goal in args.goal:
        regrade(
            goal,
            Path(args.invalid_root),
            Path(args.final_root),
            Path(args.suite),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
