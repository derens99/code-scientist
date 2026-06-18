import json
import subprocess

from code_scientist.cli import main


def test_cli_run_writes_state_and_report(tmp_path):
    out_dir = tmp_path / "demo"
    exit_code = main(
        [
            "run",
            "Find testable ideas to improve LLM coding agents",
            "--cycles",
            "1",
            "--max-hypotheses",
            "4",
            "--max-matches",
            "2",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "state.json").exists()
    assert (out_dir / "report.md").exists()
    data = json.loads((out_dir / "state.json").read_text())
    assert data["hypotheses"]


def test_cli_run_accepts_provider_options(tmp_path):
    out_dir = tmp_path / "demo"
    exit_code = main(
        [
            "run",
            "Find testable ideas to improve LLM coding agents",
            "--provider",
            "deterministic",
            "--model",
            "claude-haiku-4-5",
            "--max-tokens",
            "128",
            "--env-file",
            str(tmp_path / ".env"),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert (out_dir / "state.json").exists()


def test_cli_report_renders_existing_state(tmp_path, capsys):
    out_dir = tmp_path / "demo"
    main(["run", "Improve LLM coding agents", "--out", str(out_dir)])
    exit_code = main(["report", str(out_dir / "state.json")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Code Scientist Research Report" in captured.out


def test_uv_run_exposes_console_script():
    result = subprocess.run(
        ["uv", "run", "code-scientist", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run a bounded research cycle" in result.stdout
