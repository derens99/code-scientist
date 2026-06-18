from __future__ import annotations

import argparse
from pathlib import Path

from code_scientist.llm import DEFAULT_ANTHROPIC_MODEL
from code_scientist.reporting import render_report
from code_scientist.supervisor import load_state, run_research_cycle


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
    run_parser.add_argument("--max-tokens", type=int, default=1024)
    run_parser.add_argument("--env-file", default=".env")
    run_parser.add_argument("--out", default="runs/demo")

    report_parser = subparsers.add_parser("report", help="Render a report from state JSON.")
    report_parser.add_argument("state_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        out_dir = Path(args.out)
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
        )
        report = render_report(state)
        (out_dir / "report.md").write_text(report, encoding="utf-8")
        print(f"Wrote {out_dir / 'state.json'}")
        print(f"Wrote {out_dir / 'report.md'}")
        return 0
    if args.command == "report":
        report = render_report(load_state(args.state_json))
        print(report)
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
