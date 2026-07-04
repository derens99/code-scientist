from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from code_scientist.agent_packets import write_agent_packets
from code_scientist.baselines import run_baseline_research
from code_scientist.benchmarks import (
    load_benchmark_fixture,
    run_external_benchmark_comparison,
    run_benchmark_suite,
    run_benchmark_suite_comparison,
    summarize_benchmark_comparison_study,
)
from code_scientist.evidence import EvidenceStore
from code_scientist.evidence import merge_evidence
from code_scientist.evaluation import (
    assemble_capability_review_fixture,
    assemble_feedback_loop_review_fixture,
    assemble_preference_review_fixture,
    build_capability_review_packet,
    build_feedback_loop_review_packet,
    build_preference_review_packet,
    evaluate_capability_proxy,
    load_capability_evaluation_fixtures,
    load_capability_review_fixtures,
    load_feedback_loop_evaluation_fixtures,
    load_feedback_loop_review_fixtures,
    load_preference_review_fixtures,
    load_prospective_evaluation_fixtures,
    record_scaling_curve_point,
    run_prospective_validation_manifest,
)
from code_scientist.llm import DEFAULT_ANTHROPIC_MODEL
from code_scientist.models import UserFeedback, stable_id
from code_scientist.reporting import (
    render_benchmark_comparison_study_report,
    render_capability_study_report,
    render_report,
)
from code_scientist.safety import (
    load_safety_policies,
    run_safety_red_team_suite,
    screen_evidence_sources,
    summarize_safety_red_team_suite,
)
from code_scientist.study_assets import write_paper_study_kit, write_paper_study_materials
from code_scientist.supervisor import load_state, run_continuous_research, run_research_cycle


@dataclass(frozen=True)
class StudyGoalSpec:
    id: str
    objective: str
    cycles: int | None = None
    max_hypotheses: int | None = None
    max_matches: int | None = None
    scaling_label: str = ""
    scaling_baseline_score: float | None = None
    auto_capability_eval: bool | None = None
    baseline_name: str = ""
    baseline_score: float | None = None
    baseline_method: str = "single_shot"
    baseline_max_hypotheses: int = 1
    tool_budget: int | None = None
    goal_brief_paths: list[str] = field(default_factory=list)
    safety_policy_paths: list[str] = field(default_factory=list)
    benchmark_fixtures: list[str] = field(default_factory=list)
    benchmark_suites: list[str] = field(default_factory=list)
    external_benchmark_manifests: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    evidence_indexes: list[str] = field(default_factory=list)
    repo_search_paths: list[str] = field(default_factory=list)
    web_evidence_urls: list[str] = field(default_factory=list)
    web_search_queries: list[str] = field(default_factory=list)
    literature_search_queries: list[str] = field(default_factory=list)
    capability_eval_fixtures: list[str] = field(default_factory=list)
    prospective_eval_fixtures: list[str] = field(default_factory=list)
    prospective_validation_manifests: list[str] = field(default_factory=list)
    feedback_loop_eval_fixtures: list[str] = field(default_factory=list)
    feedback_loop_review_fixtures: list[str] = field(default_factory=list)
    capability_review_fixtures: list[str] = field(default_factory=list)
    preference_review_fixtures: list[str] = field(default_factory=list)
    safety_red_team: bool | None = None
    web_crawl_depth: int | None = None
    web_search_fetch: bool | None = None
    web_search_crawl_depth: int | None = None
    literature_full_text: bool | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-scientist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bounded research cycle.")
    run_parser.add_argument("objective")
    run_parser.add_argument("--cycles", type=int, default=1)
    run_parser.add_argument("--max-hypotheses", type=int, default=6)
    run_parser.add_argument("--max-matches", type=int, default=4)
    run_parser.add_argument("--provider", choices=["deterministic", "anthropic"], default="deterministic")
    run_parser.add_argument("--model", default=DEFAULT_ANTHROPIC_MODEL)
    run_parser.add_argument("--max-tokens", type=int, default=4096)
    run_parser.add_argument("--env-file", default=".env")
    run_parser.add_argument("--benchmark-fixture", action="append", default=[])
    run_parser.add_argument("--benchmark-suite", action="append", default=[])
    run_parser.add_argument("--goal-brief", action="append", default=[])
    run_parser.add_argument("--safety-policy", action="append", default=[])
    run_parser.add_argument("--evidence-path", action="append", default=[])
    run_parser.add_argument("--evidence-index", action="append", default=[])
    run_parser.add_argument("--repo-search-path", action="append", default=[])
    run_parser.add_argument("--web-evidence-url", action="append", default=[])
    run_parser.add_argument("--web-crawl-depth", type=int, default=0)
    run_parser.add_argument("--web-search-query", action="append", default=[])
    run_parser.add_argument("--web-search-fetch", action="store_true")
    run_parser.add_argument("--web-search-crawl-depth", type=int, default=0)
    run_parser.add_argument("--literature-search-query", action="append", default=[])
    run_parser.add_argument("--literature-full-text", action="store_true")
    run_parser.add_argument("--capability-eval-fixture", action="append", default=[])
    run_parser.add_argument("--capability-review-fixture", action="append", default=[])
    run_parser.add_argument("--preference-review-fixture", action="append", default=[])
    run_parser.add_argument("--prospective-eval-fixture", action="append", default=[])
    run_parser.add_argument("--feedback-loop-eval-fixture", action="append", default=[])
    run_parser.add_argument("--feedback-loop-review-fixture", action="append", default=[])
    run_parser.add_argument("--continuous", action="store_true")
    run_parser.add_argument("--interval-seconds", type=float, default=60)
    run_parser.add_argument("--max-wall-minutes", type=float)
    run_parser.add_argument("--max-continuous-cycles", type=int)
    run_parser.add_argument("--out", default="runs/demo")

    baseline_parser = subparsers.add_parser("baseline-run", help="Write a deterministic baseline run state.")
    baseline_parser.add_argument("objective")
    baseline_parser.add_argument("--method", default="single_shot")
    baseline_parser.add_argument("--max-hypotheses", type=int, default=1)
    baseline_parser.add_argument("--out", required=True)

    index_parser = subparsers.add_parser("index", help="Build a reusable local evidence index.")
    index_parser.add_argument("--evidence-path", action="append", required=True)
    index_parser.add_argument("--safety-policy", action="append", default=[])
    index_parser.add_argument("--name", default="")
    index_parser.add_argument("--out", required=True)

    paper_study_kit_parser = subparsers.add_parser(
        "paper-study-kit",
        help="Write a local paper-style capability study kit.",
    )
    paper_study_kit_parser.add_argument("--out", required=True)

    paper_study_materials_parser = subparsers.add_parser(
        "paper-study-materials",
        help="Write populated paper-style review materials from a study-run directory.",
    )
    paper_study_materials_parser.add_argument("study_run_dir")
    paper_study_materials_parser.add_argument("--out", required=True)
    paper_study_materials_parser.add_argument("--seed", default="")

    review_packet_parser = subparsers.add_parser(
        "feedback-loop-review-packet",
        help="Build a blinded feedback-loop review packet and private answer key.",
    )
    review_packet_parser.add_argument("spec_json")
    review_packet_parser.add_argument("--out", required=True)
    review_packet_parser.add_argument("--seed", default="")

    capability_review_packet_parser = subparsers.add_parser(
        "capability-review-packet",
        help="Build a blinded baseline-vs-Code Scientist capability review packet and private answer key.",
    )
    capability_review_packet_parser.add_argument("spec_json")
    capability_review_packet_parser.add_argument("--out", required=True)
    capability_review_packet_parser.add_argument("--seed", default="")

    capability_review_fixture_parser = subparsers.add_parser(
        "capability-review-fixture",
        help="Merge returned capability review scores with a private answer key.",
    )
    capability_review_fixture_parser.add_argument("score_template_json")
    capability_review_fixture_parser.add_argument("--answer-key", required=True)
    capability_review_fixture_parser.add_argument("--out", required=True)
    capability_review_fixture_parser.add_argument("--human-rubric-scale", type=float)

    preference_review_packet_parser = subparsers.add_parser(
        "preference-review-packet",
        help="Build a blinded baseline-vs-Code Scientist preference review packet and private answer key.",
    )
    preference_review_packet_parser.add_argument("spec_json")
    preference_review_packet_parser.add_argument("--out", required=True)
    preference_review_packet_parser.add_argument("--seed", default="")

    preference_review_fixture_parser = subparsers.add_parser(
        "preference-review-fixture",
        help="Merge returned preference review choices with a private answer key.",
    )
    preference_review_fixture_parser.add_argument("score_template_json")
    preference_review_fixture_parser.add_argument("--answer-key", required=True)
    preference_review_fixture_parser.add_argument("--out", required=True)

    feedback_loop_review_fixture_parser = subparsers.add_parser(
        "feedback-loop-review-fixture",
        help="Merge returned feedback-loop review scores with a private answer key.",
    )
    feedback_loop_review_fixture_parser.add_argument("score_template_json")
    feedback_loop_review_fixture_parser.add_argument("--answer-key", required=True)
    feedback_loop_review_fixture_parser.add_argument("--out", required=True)

    prospective_validation_parser = subparsers.add_parser(
        "prospective-validation-run",
        help="Run a no-shell prospective validation manifest for a saved state.",
    )
    prospective_validation_parser.add_argument("state_json")
    prospective_validation_parser.add_argument("manifest_json")
    prospective_validation_parser.add_argument("--work-dir", required=True)
    prospective_validation_parser.add_argument("--out", required=True)

    evaluation_return_parser = subparsers.add_parser(
        "evaluation-return",
        help="Append returned review and validation fixtures to an existing run directory.",
    )
    evaluation_return_parser.add_argument("run_dir")
    evaluation_return_parser.add_argument("--capability-eval-fixture", action="append", default=[])
    evaluation_return_parser.add_argument("--capability-review-fixture", action="append", default=[])
    evaluation_return_parser.add_argument("--preference-review-fixture", action="append", default=[])
    evaluation_return_parser.add_argument("--prospective-eval-fixture", action="append", default=[])
    evaluation_return_parser.add_argument("--feedback-loop-eval-fixture", action="append", default=[])
    evaluation_return_parser.add_argument("--feedback-loop-review-fixture", action="append", default=[])

    source_attachment_parser = subparsers.add_parser(
        "source-attachment",
        help="Append local evidence sources or evidence indexes to an existing run directory.",
    )
    source_attachment_parser.add_argument("run_dir")
    source_attachment_parser.add_argument("--evidence-path", action="append", default=[])
    source_attachment_parser.add_argument("--evidence-index", action="append", default=[])

    agent_packets_parser = subparsers.add_parser(
        "agent-packets",
        help="Write host-agent subagent prompt packets from a saved run state.",
    )
    agent_packets_parser.add_argument("state_json")
    agent_packets_parser.add_argument("--out", required=True)
    agent_packets_parser.add_argument("--limit", type=int, default=3)

    benchmark_comparison_parser = subparsers.add_parser(
        "benchmark-suite-comparison",
        help="Compare baseline and Code Scientist saved states against the same benchmark suite.",
    )
    benchmark_comparison_parser.add_argument("suite_json")
    benchmark_comparison_parser.add_argument("--baseline-state", required=True)
    benchmark_comparison_parser.add_argument("--candidate-state", required=True)
    benchmark_comparison_parser.add_argument("--baseline-name", default="baseline")
    benchmark_comparison_parser.add_argument("--candidate-name", default="code_scientist")
    benchmark_comparison_parser.add_argument("--out", required=True)

    external_benchmark_comparison_parser = subparsers.add_parser(
        "external-benchmark-comparison",
        help="Run manifest-defined external benchmark commands for two saved states.",
    )
    external_benchmark_comparison_parser.add_argument("manifest_json")
    external_benchmark_comparison_parser.add_argument("--baseline-state", required=True)
    external_benchmark_comparison_parser.add_argument("--candidate-state", required=True)
    external_benchmark_comparison_parser.add_argument("--work-dir", required=True)
    external_benchmark_comparison_parser.add_argument("--out", required=True)

    benchmark_study_parser = subparsers.add_parser(
        "benchmark-comparison-study",
        help="Run a manifest of saved-state benchmark comparisons and write aggregate study artifacts.",
    )
    benchmark_study_parser.add_argument("manifest_json")
    benchmark_study_parser.add_argument("--out", required=True)

    benchmark_study_run_parser = subparsers.add_parser(
        "benchmark-study-run",
        help="Run baseline and Code Scientist arms for benchmark-suite comparison goals.",
    )
    benchmark_study_run_parser.add_argument("manifest_json")
    benchmark_study_run_parser.add_argument("--cycles", type=int, default=1)
    benchmark_study_run_parser.add_argument("--max-hypotheses", type=int, default=6)
    benchmark_study_run_parser.add_argument("--max-matches", type=int, default=4)
    benchmark_study_run_parser.add_argument("--provider", choices=["deterministic", "anthropic"], default="deterministic")
    benchmark_study_run_parser.add_argument("--model", default=DEFAULT_ANTHROPIC_MODEL)
    benchmark_study_run_parser.add_argument("--max-tokens", type=int, default=4096)
    benchmark_study_run_parser.add_argument("--env-file", default=".env")
    benchmark_study_run_parser.add_argument("--benchmark-suite", action="append", default=[])
    benchmark_study_run_parser.add_argument("--external-benchmark-manifest", action="append", default=[])
    benchmark_study_run_parser.add_argument("--safety-policy", action="append", default=[])
    benchmark_study_run_parser.add_argument("--out", required=True)

    report_parser = subparsers.add_parser("report", help="Render a report from state JSON.")
    report_parser.add_argument("state_json")

    study_parser = subparsers.add_parser("study", help="Aggregate capability-study metrics from state JSON.")
    study_parser.add_argument("state_json", nargs="+")
    study_parser.add_argument("--out")

    study_run_parser = subparsers.add_parser("study-run", help="Run a multi-goal capability study manifest.")
    study_run_parser.add_argument("manifest_json")
    study_run_parser.add_argument("--cycles", type=int, default=1)
    study_run_parser.add_argument("--max-hypotheses", type=int, default=6)
    study_run_parser.add_argument("--max-matches", type=int, default=4)
    study_run_parser.add_argument("--provider", choices=["deterministic", "anthropic"], default="deterministic")
    study_run_parser.add_argument("--model", default=DEFAULT_ANTHROPIC_MODEL)
    study_run_parser.add_argument("--max-tokens", type=int, default=4096)
    study_run_parser.add_argument("--env-file", default=".env")
    study_run_parser.add_argument("--benchmark-fixture", action="append", default=[])
    study_run_parser.add_argument("--benchmark-suite", action="append", default=[])
    study_run_parser.add_argument("--external-benchmark-manifest", action="append", default=[])
    study_run_parser.add_argument("--goal-brief", action="append", default=[])
    study_run_parser.add_argument("--safety-policy", action="append", default=[])
    study_run_parser.add_argument("--evidence-path", action="append", default=[])
    study_run_parser.add_argument("--evidence-index", action="append", default=[])
    study_run_parser.add_argument("--repo-search-path", action="append", default=[])
    study_run_parser.add_argument("--web-evidence-url", action="append", default=[])
    study_run_parser.add_argument("--web-crawl-depth", type=int, default=0)
    study_run_parser.add_argument("--web-search-query", action="append", default=[])
    study_run_parser.add_argument("--web-search-fetch", action="store_true")
    study_run_parser.add_argument("--web-search-crawl-depth", type=int, default=0)
    study_run_parser.add_argument("--literature-search-query", action="append", default=[])
    study_run_parser.add_argument("--literature-full-text", action="store_true")
    study_run_parser.add_argument("--capability-eval-fixture", action="append", default=[])
    study_run_parser.add_argument("--capability-review-fixture", action="append", default=[])
    study_run_parser.add_argument("--preference-review-fixture", action="append", default=[])
    study_run_parser.add_argument("--prospective-eval-fixture", action="append", default=[])
    study_run_parser.add_argument("--prospective-validation-manifest", action="append", default=[])
    study_run_parser.add_argument("--feedback-loop-eval-fixture", action="append", default=[])
    study_run_parser.add_argument("--feedback-loop-review-fixture", action="append", default=[])
    study_run_parser.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        out_dir = Path(args.out)
        benchmark_results = [
            load_benchmark_fixture(path) for path in args.benchmark_fixture
        ]
        if args.continuous:
            def write_report(state):
                (out_dir / "report.md").write_text(render_report(state), encoding="utf-8")

            state = run_continuous_research(
                objective=args.objective,
                max_hypotheses=args.max_hypotheses,
                max_matches=args.max_matches,
                out_dir=out_dir,
                provider=args.provider,
                model=args.model,
                max_tokens=args.max_tokens,
                env_file=args.env_file,
                goal_brief_paths=args.goal_brief,
                safety_policy_paths=args.safety_policy,
                benchmark_results=benchmark_results,
                evidence_paths=args.evidence_path,
                evidence_index_paths=args.evidence_index,
                repo_search_paths=args.repo_search_path,
                web_evidence_urls=args.web_evidence_url,
                web_crawl_depth=args.web_crawl_depth,
                web_search_queries=args.web_search_query,
                web_search_fetch=args.web_search_fetch,
                web_search_crawl_depth=args.web_search_crawl_depth,
                literature_search_queries=args.literature_search_query,
                literature_full_text=args.literature_full_text,
                capability_evaluation_paths=args.capability_eval_fixture,
                interval_seconds=args.interval_seconds,
                max_wall_minutes=args.max_wall_minutes,
                max_continuous_cycles=args.max_continuous_cycles,
                after_cycle=write_report,
            )
        else:
            state = run_research_cycle(
                objective=args.objective,
                cycles=args.cycles,
                max_hypotheses=args.max_hypotheses,
                max_matches=args.max_matches,
                out_dir=out_dir,
                provider=args.provider,
                model=args.model,
                max_tokens=args.max_tokens,
                env_file=args.env_file,
                goal_brief_paths=args.goal_brief,
                safety_policy_paths=args.safety_policy,
                benchmark_results=benchmark_results,
                evidence_paths=args.evidence_path,
                evidence_index_paths=args.evidence_index,
                repo_search_paths=args.repo_search_path,
                web_evidence_urls=args.web_evidence_url,
                web_crawl_depth=args.web_crawl_depth,
                web_search_queries=args.web_search_query,
                web_search_fetch=args.web_search_fetch,
                web_search_crawl_depth=args.web_search_crawl_depth,
                literature_search_queries=args.literature_search_query,
                literature_full_text=args.literature_full_text,
                capability_evaluation_paths=args.capability_eval_fixture,
            )
        state = _append_benchmark_suite_results(state, args.benchmark_suite)
        state = _append_capability_review_evaluations(state, args.capability_review_fixture)
        state = _append_preference_review_evaluations(state, args.preference_review_fixture)
        state = _append_prospective_evaluations(state, args.prospective_eval_fixture)
        state = _append_feedback_loop_evaluations(
            state,
            args.feedback_loop_eval_fixture,
            args.feedback_loop_review_fixture,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "state.json").write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        report = render_report(state)
        (out_dir / "report.md").write_text(report, encoding="utf-8")
        print(f"Wrote {out_dir / 'state.json'}")
        print(f"Wrote {out_dir / 'report.md'}")
        return 0
    if args.command == "evaluation-return":
        run_dir = Path(args.run_dir)
        state = load_state(run_dir / "state.json")
        state = _append_capability_evaluations(state, args.capability_eval_fixture)
        state = _append_capability_review_evaluations(state, args.capability_review_fixture)
        state = _append_preference_review_evaluations(state, args.preference_review_fixture)
        state = _append_prospective_evaluations(state, args.prospective_eval_fixture)
        state = _append_feedback_loop_evaluations(
            state,
            args.feedback_loop_eval_fixture,
            args.feedback_loop_review_fixture,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        (run_dir / "report.md").write_text(render_report(state), encoding="utf-8")
        print(f"Wrote {run_dir / 'state.json'}")
        print(f"Wrote {run_dir / 'report.md'}")
        return 0
    if args.command == "source-attachment":
        run_dir = Path(args.run_dir)
        state = load_state(run_dir / "state.json")
        state = _append_source_attachments(
            state,
            evidence_paths=args.evidence_path,
            evidence_index_paths=args.evidence_index,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        (run_dir / "report.md").write_text(render_report(state), encoding="utf-8")
        print(f"Wrote {run_dir / 'state.json'}")
        print(f"Wrote {run_dir / 'report.md'}")
        return 0
    if args.command == "agent-packets":
        index = write_agent_packets(
            load_state(args.state_json),
            state_path=args.state_json,
            out_dir=args.out,
            limit=args.limit,
        )
        output = Path(args.out)
        print(f"Wrote {output / 'packet-index.json'}")
        for packet in index["packets"]:
            print(f"Wrote {output / packet['path']}")
        return 0
    if args.command == "baseline-run":
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        state = run_baseline_research(
            args.objective,
            method=args.method,
            max_hypotheses=args.max_hypotheses,
        )
        (out_dir / "state.json").write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        (out_dir / "report.md").write_text(render_report(state), encoding="utf-8")
        print(f"Wrote {out_dir / 'state.json'}")
        print(f"Wrote {out_dir / 'report.md'}")
        return 0
    if args.command == "index":
        store = EvidenceStore.from_paths(args.evidence_path)
        safety_findings = []
        if args.safety_policy:
            allowed_evidence, safety_findings = screen_evidence_sources(
                store.evidence,
                safety_policies=load_safety_policies(args.safety_policy),
            )
            store = EvidenceStore(allowed_evidence)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        index_data = store.to_index(name=args.name)
        if safety_findings:
            index_data["evidence_safety_findings"] = [finding.to_dict() for finding in safety_findings]
        output.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        print(f"Indexed {len(store.evidence)} evidence records")
        if safety_findings:
            rejected = len([finding for finding in safety_findings if not finding.allowed])
            audited = len(safety_findings) - rejected
            print(f"Safety-screened {len(safety_findings)} findings ({rejected} rejected, {audited} allowed audits)")
        return 0
    if args.command == "paper-study-kit":
        written = write_paper_study_kit(args.out)
        for path in written:
            print(f"Wrote {path}")
        return 0
    if args.command == "paper-study-materials":
        written = write_paper_study_materials(args.study_run_dir, args.out, seed=args.seed)
        for path in written:
            print(f"Wrote {path}")
        return 0
    if args.command == "feedback-loop-review-packet":
        spec_path = Path(args.spec_json)
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        packet, answer_key, score_template = build_feedback_loop_review_packet(data, seed=args.seed)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        packet_path = output / "review-packet.json"
        answer_key_path = output / "answer-key.json"
        score_template_path = output / "score-template.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
        score_template_path.write_text(json.dumps(score_template, indent=2), encoding="utf-8")
        print(f"Wrote {packet_path}")
        print(f"Wrote {answer_key_path}")
        print(f"Wrote {score_template_path}")
        return 0
    if args.command == "capability-review-packet":
        spec_path = Path(args.spec_json)
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        packet, answer_key, score_template = build_capability_review_packet(data, seed=args.seed)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        packet_path = output / "capability-review-packet.json"
        answer_key_path = output / "capability-review-answer-key.json"
        score_template_path = output / "capability-review-score-template.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
        score_template_path.write_text(json.dumps(score_template, indent=2), encoding="utf-8")
        print(f"Wrote {packet_path}")
        print(f"Wrote {answer_key_path}")
        print(f"Wrote {score_template_path}")
        return 0
    if args.command == "preference-review-packet":
        spec_path = Path(args.spec_json)
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        packet, answer_key, score_template = build_preference_review_packet(data, seed=args.seed)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        packet_path = output / "preference-review-packet.json"
        answer_key_path = output / "preference-review-answer-key.json"
        score_template_path = output / "preference-review-template.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
        score_template_path.write_text(json.dumps(score_template, indent=2), encoding="utf-8")
        print(f"Wrote {packet_path}")
        print(f"Wrote {answer_key_path}")
        print(f"Wrote {score_template_path}")
        return 0
    if args.command == "capability-review-fixture":
        fixture = assemble_capability_review_fixture(
            args.score_template_json,
            args.answer_key,
            human_rubric_scale=args.human_rubric_scale,
        )
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "preference-review-fixture":
        fixture = assemble_preference_review_fixture(args.score_template_json, args.answer_key)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "feedback-loop-review-fixture":
        fixture = assemble_feedback_loop_review_fixture(args.score_template_json, args.answer_key)
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "prospective-validation-run":
        state = load_state(args.state_json)
        fixture = run_prospective_validation_manifest(
            args.manifest_json,
            state,
            work_dir=args.work_dir,
        )
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "benchmark-suite-comparison":
        baseline_state = load_state(args.baseline_state)
        candidate_state = load_state(args.candidate_state)
        result = run_benchmark_suite_comparison(
            args.suite_json,
            baseline_state.hypotheses,
            candidate_state.hypotheses,
            baseline_name=args.baseline_name,
            candidate_name=args.candidate_name,
        )
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "external-benchmark-comparison":
        baseline_state = load_state(args.baseline_state)
        candidate_state = load_state(args.candidate_state)
        result = run_external_benchmark_comparison(
            args.manifest_json,
            baseline_state.hypotheses,
            candidate_state.hypotheses,
            work_dir=args.work_dir,
        )
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"Wrote {output}")
        return 0
    if args.command == "benchmark-comparison-study":
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        results = _benchmark_comparison_results_from_manifest(
            args.manifest_json,
            generated_baseline_root=output / "baselines",
        )
        summary = summarize_benchmark_comparison_study(results)
        results_path = output / "benchmark-comparisons.json"
        report_path = output / "benchmark-study.md"
        results_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "results": [result.to_dict() for result in results],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report_path.write_text(
            render_benchmark_comparison_study_report(results, summary),
            encoding="utf-8",
        )
        print(f"Wrote {results_path}")
        print(f"Wrote {report_path}")
        return 0
    if args.command == "benchmark-study-run":
        manifest_path = Path(args.manifest_json)
        goals = _study_goals_from_manifest(manifest_path)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        results = []
        for goal in goals:
            suite_paths = _benchmark_suite_paths_for_goal(manifest_path, args.benchmark_suite, goal)
            external_manifest_paths = _external_benchmark_manifest_paths_for_goal(
                manifest_path,
                args.external_benchmark_manifest,
                goal,
            )
            if not suite_paths and not external_manifest_paths:
                raise ValueError(
                    f"Benchmark study goal {goal.id} must include at least one benchmark suite "
                    "or external benchmark manifest."
                )
            run_dir = output / goal.id
            baseline_dir = run_dir / "baseline"
            candidate_dir = run_dir / "code-scientist"
            baseline_state = run_baseline_research(
                goal.objective,
                method=goal.baseline_method,
                max_hypotheses=goal.baseline_max_hypotheses,
            )
            baseline_dir.mkdir(parents=True, exist_ok=True)
            baseline_state_path = baseline_dir / "state.json"
            baseline_state_path.write_text(json.dumps(baseline_state.to_dict(), indent=2), encoding="utf-8")
            (baseline_dir / "report.md").write_text(render_report(baseline_state), encoding="utf-8")

            cycles = goal.cycles if goal.cycles is not None else args.cycles
            max_hypotheses = goal.max_hypotheses if goal.max_hypotheses is not None else args.max_hypotheses
            max_matches = goal.max_matches if goal.max_matches is not None else args.max_matches
            candidate_state = run_research_cycle(
                objective=goal.objective,
                cycles=cycles,
                max_hypotheses=max_hypotheses,
                max_matches=max_matches,
                out_dir=candidate_dir,
                provider=args.provider,
                model=args.model,
                max_tokens=args.max_tokens,
                env_file=args.env_file,
                goal_brief_paths=goal.goal_brief_paths,
                safety_policy_paths=[*args.safety_policy, *goal.safety_policy_paths],
                evidence_paths=goal.evidence_paths,
                evidence_index_paths=goal.evidence_indexes,
                repo_search_paths=goal.repo_search_paths,
                web_evidence_urls=goal.web_evidence_urls,
                web_crawl_depth=goal.web_crawl_depth or 0,
                web_search_queries=goal.web_search_queries,
                web_search_fetch=bool(goal.web_search_fetch),
                web_search_crawl_depth=goal.web_search_crawl_depth or 0,
                literature_search_queries=goal.literature_search_queries,
                literature_full_text=bool(goal.literature_full_text),
                capability_evaluation_paths=goal.capability_eval_fixtures,
            )
            candidate_dir.mkdir(parents=True, exist_ok=True)
            (candidate_dir / "state.json").write_text(json.dumps(candidate_state.to_dict(), indent=2), encoding="utf-8")
            (candidate_dir / "report.md").write_text(render_report(candidate_state), encoding="utf-8")

            for suite_path in suite_paths:
                results.append(
                    run_benchmark_suite_comparison(
                        suite_path,
                        baseline_state.hypotheses,
                        candidate_state.hypotheses,
                        baseline_name=goal.baseline_name or goal.baseline_method,
                        candidate_name="code_scientist",
                    )
                )
            for external_manifest_path in external_manifest_paths:
                results.append(
                    run_external_benchmark_comparison(
                        external_manifest_path,
                        baseline_state.hypotheses,
                        candidate_state.hypotheses,
                        work_dir=run_dir / "external-benchmarks" / _safe_slug(external_manifest_path.stem),
                    )
                )
            print(f"Wrote {baseline_state_path}")
            print(f"Wrote {candidate_dir / 'state.json'}")
        summary = summarize_benchmark_comparison_study(results)
        results_path = output / "benchmark-comparisons.json"
        report_path = output / "benchmark-study.md"
        results_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "results": [result.to_dict() for result in results],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report_path.write_text(render_benchmark_comparison_study_report(results, summary), encoding="utf-8")
        print(f"Wrote {results_path}")
        print(f"Wrote {report_path}")
        return 0
    if args.command == "report":
        report = render_report(load_state(args.state_json))
        print(report)
        return 0
    if args.command == "study":
        states = [load_state(path) for path in args.state_json]
        report = render_capability_study_report(states)
        if args.out:
            output = Path(args.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
            print(f"Wrote {output}")
        else:
            print(report)
        return 0
    if args.command == "study-run":
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        global_benchmark_results = [load_benchmark_fixture(path) for path in args.benchmark_fixture]
        states = []
        for goal in _study_goals_from_manifest(args.manifest_json):
            run_dir = out_dir / goal.id
            cycles = goal.cycles if goal.cycles is not None else args.cycles
            max_hypotheses = goal.max_hypotheses if goal.max_hypotheses is not None else args.max_hypotheses
            max_matches = goal.max_matches if goal.max_matches is not None else args.max_matches
            benchmark_results = [
                *global_benchmark_results,
                *[load_benchmark_fixture(path) for path in goal.benchmark_fixtures],
            ]
            state = run_research_cycle(
                objective=goal.objective,
                cycles=cycles,
                max_hypotheses=max_hypotheses,
                max_matches=max_matches,
                out_dir=run_dir,
                provider=args.provider,
                model=args.model,
                max_tokens=args.max_tokens,
                env_file=args.env_file,
                goal_brief_paths=[*args.goal_brief, *goal.goal_brief_paths],
                safety_policy_paths=[*args.safety_policy, *goal.safety_policy_paths],
                benchmark_results=benchmark_results,
                evidence_paths=[*args.evidence_path, *goal.evidence_paths],
                evidence_index_paths=[*args.evidence_index, *goal.evidence_indexes],
                repo_search_paths=[*args.repo_search_path, *goal.repo_search_paths],
                web_evidence_urls=[*args.web_evidence_url, *goal.web_evidence_urls],
                web_crawl_depth=goal.web_crawl_depth if goal.web_crawl_depth is not None else args.web_crawl_depth,
                web_search_queries=[*args.web_search_query, *goal.web_search_queries],
                web_search_fetch=args.web_search_fetch or bool(goal.web_search_fetch),
                web_search_crawl_depth=(
                    goal.web_search_crawl_depth
                    if goal.web_search_crawl_depth is not None
                    else args.web_search_crawl_depth
                ),
                literature_search_queries=[*args.literature_search_query, *goal.literature_search_queries],
                literature_full_text=args.literature_full_text or bool(goal.literature_full_text),
                capability_evaluation_paths=[*args.capability_eval_fixture, *goal.capability_eval_fixtures],
            )
            state = _append_benchmark_suite_results(
                state,
                [
                    *args.benchmark_suite,
                    *[
                        str(_resolve_manifest_path(Path(args.manifest_json), raw_path))
                        for raw_path in goal.benchmark_suites
                    ],
                ],
            )
            state = _append_external_benchmark_results(
                state,
                Path(args.manifest_json),
                args.external_benchmark_manifest,
                goal,
                run_dir,
            )
            state = _append_capability_review_evaluations(
                state,
                [*args.capability_review_fixture, *goal.capability_review_fixtures],
            )
            state = _append_preference_review_evaluations(
                state,
                [*args.preference_review_fixture, *goal.preference_review_fixtures],
            )
            state = _append_prospective_evaluations(
                state,
                [*args.prospective_eval_fixture, *goal.prospective_eval_fixtures],
            )
            state = _append_prospective_validation_results(
                state,
                Path(args.manifest_json),
                args.prospective_validation_manifest,
                goal,
                run_dir,
            )
            state = _append_feedback_loop_evaluations(
                state,
                [*args.feedback_loop_eval_fixture, *goal.feedback_loop_eval_fixtures],
                [*args.feedback_loop_review_fixture, *goal.feedback_loop_review_fixtures],
            )
            state = _append_safety_red_team_evaluation(state, goal)
            state = _append_auto_capability_evaluation(state, goal)
            state = _append_scaling_curve_point(
                state,
                goal=goal,
                cycles=cycles,
                max_hypotheses=max_hypotheses,
                max_matches=max_matches,
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.json").write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
            (run_dir / "report.md").write_text(render_report(state), encoding="utf-8")
            states.append(state)
            print(f"Wrote {run_dir / 'state.json'}")
            print(f"Wrote {run_dir / 'report.md'}")
        study_report = render_capability_study_report(states)
        (out_dir / "study.md").write_text(study_report, encoding="utf-8")
        print(f"Wrote {out_dir / 'study.md'}")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def _benchmark_comparison_results_from_manifest(
    path: str | Path,
    *,
    generated_baseline_root: Path | None = None,
):
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("comparisons"), list):
        raise ValueError("Benchmark comparison manifest must be a JSON object with a comparisons list.")
    raw_comparisons = data["comparisons"]
    if not raw_comparisons:
        raise ValueError("Benchmark comparison manifest must include at least one comparison.")

    results = []
    for index, raw_comparison in enumerate(raw_comparisons, start=1):
        if not isinstance(raw_comparison, dict):
            raise ValueError(f"Benchmark comparison {index} must be a JSON object.")
        label = f"comparisons[{index}]"
        suite_path = _resolve_manifest_path(
            manifest_path,
            _required_manifest_string(raw_comparison, "suite", label),
        )
        candidate_state_path = _resolve_manifest_path(
            manifest_path,
            _required_manifest_string(raw_comparison, "candidate_state", label),
        )
        baseline_state_path = _baseline_state_path_for_comparison(
            raw_comparison,
            manifest_path=manifest_path,
            generated_baseline_root=generated_baseline_root,
            label=label,
            index=index,
        )
        baseline_state = load_state(baseline_state_path)
        candidate_state = load_state(candidate_state_path)
        results.append(
            run_benchmark_suite_comparison(
                suite_path,
                baseline_state.hypotheses,
                candidate_state.hypotheses,
                baseline_name=str(raw_comparison.get("baseline_name") or "baseline"),
                candidate_name=str(raw_comparison.get("candidate_name") or "code_scientist"),
            )
        )
    return results


def _baseline_state_path_for_comparison(
    raw_comparison: dict[str, object],
    *,
    manifest_path: Path,
    generated_baseline_root: Path | None,
    label: str,
    index: int,
) -> Path:
    baseline_state = str(raw_comparison.get("baseline_state", "")).strip()
    if baseline_state:
        return _resolve_manifest_path(manifest_path, baseline_state)

    if generated_baseline_root is None:
        raise ValueError(f"{label}.baseline_state is required when generated baselines are disabled.")
    baseline_objective = _required_manifest_string(raw_comparison, "baseline_objective", label)
    baseline_method = str(raw_comparison.get("baseline_method") or "single_shot")
    baseline_max_hypotheses = _optional_int(
        raw_comparison.get("baseline_max_hypotheses"),
        f"{label}.baseline_max_hypotheses",
    ) or 1
    comparison_id = _safe_slug(str(raw_comparison.get("id", "")).strip()) or f"comparison-{index}"
    baseline_dir = generated_baseline_root / comparison_id
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline = run_baseline_research(
        baseline_objective,
        method=baseline_method,
        max_hypotheses=baseline_max_hypotheses,
    )
    baseline_state_path = baseline_dir / "state.json"
    baseline_state_path.write_text(json.dumps(baseline.to_dict(), indent=2), encoding="utf-8")
    (baseline_dir / "report.md").write_text(render_report(baseline), encoding="utf-8")
    return baseline_state_path


def _benchmark_suite_paths_for_goal(
    manifest_path: Path,
    global_suite_paths: list[str],
    goal: StudyGoalSpec,
) -> list[Path]:
    paths: list[Path] = []
    for raw_path in global_suite_paths:
        if str(raw_path).strip():
            paths.append(Path(raw_path))
    for raw_path in goal.benchmark_suites:
        if str(raw_path).strip():
            paths.append(_resolve_manifest_path(manifest_path, raw_path))
    return paths


def _external_benchmark_manifest_paths_for_goal(
    manifest_path: Path,
    global_manifest_paths: list[str],
    goal: StudyGoalSpec,
) -> list[Path]:
    paths: list[Path] = []
    for raw_path in global_manifest_paths:
        if str(raw_path).strip():
            paths.append(Path(raw_path))
    for raw_path in goal.external_benchmark_manifests:
        if str(raw_path).strip():
            paths.append(_resolve_manifest_path(manifest_path, raw_path))
    return paths


def _required_manifest_string(data: dict[str, object], key: str, label: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{label}.{key} is required.")
    return value


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _study_goals_from_manifest(path: str | Path) -> list[StudyGoalSpec]:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("goals"), list):
        raise ValueError("Study manifest must be a JSON object with a goals list.")

    goals: list[StudyGoalSpec] = []
    for index, raw_goal in enumerate(data["goals"], start=1):
        if not isinstance(raw_goal, dict):
            raise ValueError(f"Study manifest goal {index} must be a JSON object.")
        objective = str(raw_goal.get("objective", "")).strip()
        if not objective:
            raise ValueError(f"Study manifest goal {index} is missing an objective.")
        goal_id = _safe_slug(str(raw_goal.get("id", "")).strip()) or f"goal-{index}"
        goals.append(
            StudyGoalSpec(
                id=goal_id,
                objective=objective,
                cycles=_optional_int(raw_goal.get("cycles"), f"goals[{index}].cycles"),
                max_hypotheses=_optional_int(raw_goal.get("max_hypotheses"), f"goals[{index}].max_hypotheses"),
                max_matches=_optional_int(raw_goal.get("max_matches"), f"goals[{index}].max_matches"),
                scaling_label=str(raw_goal.get("scaling_label", "")).strip(),
                scaling_baseline_score=_optional_float(
                    raw_goal.get("scaling_baseline_score"),
                    f"goals[{index}].scaling_baseline_score",
                ),
                auto_capability_eval=_optional_bool(
                    raw_goal.get("auto_capability_eval"),
                    f"goals[{index}].auto_capability_eval",
                ),
                baseline_name=str(raw_goal.get("baseline_name", "")).strip(),
                baseline_score=_optional_float(raw_goal.get("baseline_score"), f"goals[{index}].baseline_score"),
                baseline_method=str(raw_goal.get("baseline_method", "single_shot")).strip() or "single_shot",
                baseline_max_hypotheses=(
                    _optional_int(raw_goal.get("baseline_max_hypotheses"), f"goals[{index}].baseline_max_hypotheses")
                    or 1
                ),
                tool_budget=_optional_int(raw_goal.get("tool_budget"), f"goals[{index}].tool_budget"),
                goal_brief_paths=_string_list(raw_goal.get("goal_brief_paths"), f"goals[{index}].goal_brief_paths"),
                safety_policy_paths=_string_list(
                    raw_goal.get("safety_policy_paths"),
                    f"goals[{index}].safety_policy_paths",
                ),
                benchmark_fixtures=_string_list(raw_goal.get("benchmark_fixtures"), f"goals[{index}].benchmark_fixtures"),
                benchmark_suites=_string_list(raw_goal.get("benchmark_suites"), f"goals[{index}].benchmark_suites"),
                external_benchmark_manifests=_string_list(
                    raw_goal.get("external_benchmark_manifests"),
                    f"goals[{index}].external_benchmark_manifests",
                ),
                evidence_paths=_string_list(raw_goal.get("evidence_paths"), f"goals[{index}].evidence_paths"),
                evidence_indexes=_string_list(raw_goal.get("evidence_indexes"), f"goals[{index}].evidence_indexes"),
                repo_search_paths=_string_list(raw_goal.get("repo_search_paths"), f"goals[{index}].repo_search_paths"),
                web_evidence_urls=_string_list(raw_goal.get("web_evidence_urls"), f"goals[{index}].web_evidence_urls"),
                web_search_queries=_string_list(raw_goal.get("web_search_queries"), f"goals[{index}].web_search_queries"),
                literature_search_queries=_string_list(
                    raw_goal.get("literature_search_queries"),
                    f"goals[{index}].literature_search_queries",
                ),
                capability_eval_fixtures=_string_list(
                    raw_goal.get("capability_eval_fixtures"),
                    f"goals[{index}].capability_eval_fixtures",
                ),
                capability_review_fixtures=_string_list(
                    raw_goal.get("capability_review_fixtures"),
                    f"goals[{index}].capability_review_fixtures",
                ),
                preference_review_fixtures=_string_list(
                    raw_goal.get("preference_review_fixtures"),
                    f"goals[{index}].preference_review_fixtures",
                ),
                prospective_eval_fixtures=_string_list(
                    raw_goal.get("prospective_eval_fixtures"),
                    f"goals[{index}].prospective_eval_fixtures",
                ),
                prospective_validation_manifests=_string_list(
                    raw_goal.get("prospective_validation_manifests"),
                    f"goals[{index}].prospective_validation_manifests",
                ),
                feedback_loop_eval_fixtures=_string_list(
                    raw_goal.get("feedback_loop_eval_fixtures"),
                    f"goals[{index}].feedback_loop_eval_fixtures",
                ),
                feedback_loop_review_fixtures=_string_list(
                    raw_goal.get("feedback_loop_review_fixtures"),
                    f"goals[{index}].feedback_loop_review_fixtures",
                ),
                safety_red_team=_optional_bool(raw_goal.get("safety_red_team"), f"goals[{index}].safety_red_team"),
                web_crawl_depth=_optional_int(raw_goal.get("web_crawl_depth"), f"goals[{index}].web_crawl_depth"),
                web_search_fetch=_optional_bool(raw_goal.get("web_search_fetch"), f"goals[{index}].web_search_fetch"),
                web_search_crawl_depth=_optional_int(
                    raw_goal.get("web_search_crawl_depth"),
                    f"goals[{index}].web_search_crawl_depth",
                ),
                literature_full_text=_optional_bool(
                    raw_goal.get("literature_full_text"),
                    f"goals[{index}].literature_full_text",
                ),
            )
        )
    if not goals:
        raise ValueError("Study manifest must include at least one goal.")
    return goals


def _append_prospective_evaluations(state, paths: list[str]):
    evaluations = load_prospective_evaluation_fixtures(paths, state.hypotheses)
    if not evaluations:
        return state
    return replace(
        state,
        prospective_evaluations=[*state.prospective_evaluations, *evaluations],
    )


def _prospective_validation_manifest_paths_for_goal(
    manifest_path: Path,
    global_manifest_paths: list[str],
    goal: StudyGoalSpec,
) -> list[Path]:
    paths: list[Path] = []
    for raw_path in global_manifest_paths:
        if str(raw_path).strip():
            paths.append(Path(raw_path))
    for raw_path in goal.prospective_validation_manifests:
        if str(raw_path).strip():
            paths.append(_resolve_manifest_path(manifest_path, raw_path))
    return paths


def _append_prospective_validation_results(
    state,
    manifest_path: Path,
    global_manifest_paths: list[str],
    goal: StudyGoalSpec,
    run_dir: Path,
):
    validation_paths = _prospective_validation_manifest_paths_for_goal(
        manifest_path,
        global_manifest_paths,
        goal,
    )
    if not validation_paths:
        return state

    fixture_paths: list[str] = []
    for validation_path in validation_paths:
        work_dir = run_dir / "prospective-validations" / (_safe_slug(validation_path.stem) or "validation")
        fixture = run_prospective_validation_manifest(
            validation_path,
            state,
            work_dir=work_dir,
        )
        fixture_path = work_dir / "fixture.json"
        fixture_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        fixture_paths.append(str(fixture_path))
    return _append_prospective_evaluations(state, fixture_paths)


def _append_benchmark_suite_results(state, paths: list[str]):
    results = [run_benchmark_suite(path, state.hypotheses) for path in paths if str(path).strip()]
    if not results:
        return state
    return replace(
        state,
        benchmark_results=[*state.benchmark_results, *results],
    )


def _append_external_benchmark_results(
    state,
    manifest_path: Path,
    global_manifest_paths: list[str],
    goal: StudyGoalSpec,
    run_dir: Path,
):
    external_paths = _external_benchmark_manifest_paths_for_goal(
        manifest_path,
        global_manifest_paths,
        goal,
    )
    if not external_paths:
        return state

    baseline_state = run_baseline_research(
        goal.objective,
        method=goal.baseline_method,
        max_hypotheses=goal.baseline_max_hypotheses,
    )
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "state.json").write_text(json.dumps(baseline_state.to_dict(), indent=2), encoding="utf-8")
    (baseline_dir / "report.md").write_text(render_report(baseline_state), encoding="utf-8")

    results = [
        run_external_benchmark_comparison(
            external_path,
            baseline_state.hypotheses,
            state.hypotheses,
            work_dir=run_dir / "external-benchmarks" / _safe_slug(external_path.stem),
        )
        for external_path in external_paths
    ]
    return replace(
        state,
        benchmark_results=[*state.benchmark_results, *results],
    )


def _append_capability_review_evaluations(state, paths: list[str]):
    evaluations = load_capability_review_fixtures(paths, state.goal, state.hypotheses)
    if not evaluations:
        return state
    return replace(
        state,
        capability_evaluations=[*state.capability_evaluations, *evaluations],
    )


def _append_capability_evaluations(state, paths: list[str]):
    evaluations = load_capability_evaluation_fixtures(paths, state.goal, state.hypotheses)
    if not evaluations:
        return state
    return replace(
        state,
        capability_evaluations=[*state.capability_evaluations, *evaluations],
    )


def _append_preference_review_evaluations(state, paths: list[str]):
    evaluations = load_preference_review_fixtures(paths, state.goal, state.hypotheses)
    if not evaluations:
        return state
    return replace(
        state,
        capability_evaluations=[*state.capability_evaluations, *evaluations],
    )


def _append_feedback_loop_evaluations(
    state,
    paths: list[str],
    review_paths: list[str] | None = None,
):
    evaluations = [
        *load_feedback_loop_evaluation_fixtures(paths),
        *load_feedback_loop_review_fixtures(review_paths or []),
    ]
    if not evaluations:
        return state
    return replace(
        state,
        feedback_loop_evaluations=[*state.feedback_loop_evaluations, *evaluations],
    )


def _append_source_attachments(
    state,
    *,
    evidence_paths: list[str],
    evidence_index_paths: list[str],
):
    evidence_store = EvidenceStore()
    if evidence_paths:
        evidence_store.evidence.extend(EvidenceStore.from_paths(evidence_paths).evidence)
    if evidence_index_paths:
        evidence_store.evidence.extend(EvidenceStore.from_indexes(evidence_index_paths).evidence)
    if not evidence_store.evidence:
        return state

    allowed_evidence, safety_findings = screen_evidence_sources(evidence_store.evidence)
    attached_sources = sorted({item.source for item in allowed_evidence})
    source_feedback = []
    if attached_sources:
        source_text = ", ".join(attached_sources[:5])
        source_feedback.append(
            UserFeedback(
                id=stable_id(
                    "feedback",
                    f"{state.goal.id}:source_attachment:{source_text}:{len(state.user_feedback)}",
                ),
                kind="source_attachment",
                target_id=state.goal.id,
                content=f"Attached evidence sources: {source_text}",
                influence="scheduler_boost",
            )
        )

    return replace(
        state,
        evidence=merge_evidence(state.evidence, allowed_evidence),
        evidence_safety_findings=_merge_evidence_safety_findings(
            state.evidence_safety_findings,
            safety_findings,
        ),
        user_feedback=[*state.user_feedback, *source_feedback],
    )


def _merge_evidence_safety_findings(existing, additions):
    by_id = {item.id: item for item in existing}
    for item in additions:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def _append_safety_red_team_evaluation(state, goal: StudyGoalSpec):
    if not goal.safety_red_team:
        return state
    evaluation = summarize_safety_red_team_suite(run_safety_red_team_suite())
    return replace(
        state,
        safety_evaluations=[*state.safety_evaluations, evaluation],
    )


def _append_auto_capability_evaluation(state, goal: StudyGoalSpec):
    if not goal.auto_capability_eval:
        return state
    baseline_score = goal.baseline_score
    if baseline_score is None:
        baseline_score = goal.scaling_baseline_score
    if baseline_score is None:
        raise ValueError("Auto capability evaluation requires baseline_score or scaling_baseline_score.")
    baseline_name = goal.baseline_name or "deterministic_single_shot_proxy"
    evaluation = evaluate_capability_proxy(
        goal=state.goal,
        hypotheses=state.hypotheses,
        baseline_name=baseline_name,
        baseline_score=baseline_score,
    )
    return replace(
        state,
        capability_evaluations=[*state.capability_evaluations, evaluation],
    )


def _append_scaling_curve_point(
    state,
    goal: StudyGoalSpec,
    cycles: int,
    max_hypotheses: int,
    max_matches: int,
):
    if goal.scaling_baseline_score is None:
        return state
    if not state.capability_evaluations:
        raise ValueError("Scaling baseline scores require at least one capability evaluation for the run.")
    code_scientist_score = max(
        evaluation.code_scientist_score for evaluation in state.capability_evaluations
    )
    label = goal.scaling_label or f"{goal.id}-cycles-{cycles}-matches-{max_matches}"
    point = record_scaling_curve_point(
        label=label,
        cycles=cycles,
        task_count=len(state.task_queue),
        tool_budget=goal.tool_budget if goal.tool_budget is not None else max_hypotheses + max_matches,
        baseline_score=goal.scaling_baseline_score,
        code_scientist_score=code_scientist_score,
        notes=[f"Derived from study-run goal {goal.id}."],
    )
    return replace(
        state,
        scaling_curve=[*state.scaling_curve, point],
    )


def _string_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a string or list of strings.")
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{label} must be a boolean.")


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc


def _optional_float(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc


def _safe_slug(value: str) -> str:
    slug: list[str] = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            slug.append(char)
            previous_dash = False
        elif not previous_dash:
            slug.append("-")
            previous_dash = True
    return "".join(slug).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
