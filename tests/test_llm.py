import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from code_scientist.llm import (
    DEFAULT_ANTHROPIC_MODEL,
    PROVIDER_CHOICES,
    WORKER_PROVIDER_CHOICES,
    AnthropicHaikuClient,
    BudgetedLLMClient,
    ClaudeCLIClient,
    CodexCLIClient,
    HostAgentBridgeClient,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
    create_llm_client,
    is_llm_provider,
    llm_origin_for_provider,
    load_dotenv,
    resolve_provider_model,
)
from code_scientist.llm import _read_json_object, _strip_response_fence


def _completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=argv, returncode=returncode, stdout=stdout, stderr=stderr)


def test_strip_response_fence_handles_single_line_and_trailing_prose():
    # Single-line fenced payload must not be eaten whole.
    assert _strip_response_fence('```json{"a": 1}```') == '{"a": 1}'
    # A fenced block followed by host commentary keeps only the JSON.
    assert (
        _strip_response_fence('```json\n{"a": 1}\n```\nLet me know if that helps!')
        == '{"a": 1}'
    )
    # Plain multi-line fence and unfenced text still round-trip.
    assert _strip_response_fence('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_response_fence('{"a": 1}') == '{"a": 1}'


def test_read_json_object_treats_partial_multibyte_write_as_not_ready(tmp_path):
    path = tmp_path / "resp.json"
    # A non-atomic host writer flushed a truncated UTF-8 sequence (an em-dash's
    # first byte). read_text would raise UnicodeDecodeError; the poller must
    # treat it as not-yet-written (None), not crash.
    path.write_bytes(b'{"response": "cost \xe2')
    assert _read_json_object(path) is None
    # A complete object still parses.
    path.write_text('{"response": "ok"}', encoding="utf-8")
    assert _read_json_object(path) == {"response": "ok"}


def test_load_dotenv_reads_file_without_overriding_existing_environment(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        '\n'.join(
            [
                "# local secrets",
                'ANTHROPIC_API_KEY="from-file"',
                "export CODE_SCIENTIST_PROVIDER=anthropic",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-environment")
    monkeypatch.delenv("CODE_SCIENTIST_PROVIDER", raising=False)

    loaded = load_dotenv(env_path)

    assert loaded["ANTHROPIC_API_KEY"] == "from-file"
    assert os.environ["ANTHROPIC_API_KEY"] == "from-environment"
    assert os.environ["CODE_SCIENTIST_PROVIDER"] == "anthropic"


def test_anthropic_client_from_environment_requires_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=value\n", encoding="utf-8")

    with pytest.raises(LLMConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicHaikuClient.from_environment(env_path=env_path)


def test_anthropic_client_sends_messages_request_and_extracts_text():
    calls = []

    def transport(endpoint, headers, payload):
        calls.append((endpoint, headers, payload))
        return {"content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]}

    client = AnthropicHaikuClient(api_key="test-key", model=DEFAULT_ANTHROPIC_MODEL, transport=transport)

    text = client.complete("Generate research ideas.", max_tokens=123)

    assert text == "first\nsecond"
    endpoint, headers, payload = calls[0]
    assert endpoint == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert payload == {
        "model": DEFAULT_ANTHROPIC_MODEL,
        "max_tokens": 123,
        "messages": [{"role": "user", "content": "Generate research ideas."}],
    }


def test_anthropic_client_sanitizes_transport_errors():
    def transport(endpoint, headers, payload):
        raise RuntimeError("failed with test-key")

    client = AnthropicHaikuClient(api_key="test-key", transport=transport)

    with pytest.raises(LLMRequestError) as exc_info:
        client.complete("Generate research ideas.")

    assert "test-key" not in str(exc_info.value)


def test_anthropic_client_sends_bounded_base64_multimodal_content():
    calls = []

    def transport(endpoint, headers, payload):
        calls.append(payload)
        return {"content": [{"type": "text", "text": '{"figure_type":"line_chart"}'}]}

    client = AnthropicHaikuClient(api_key="test-key", transport=transport)

    response = client.complete_multimodal(
        "Interpret this bounded figure crop.",
        [{"media_type": "image/png", "data": "cG5nLWJ5dGVz"}],
        max_tokens=222,
    )

    assert response == '{"figure_type":"line_chart"}'
    content = calls[0]["messages"][0]["content"]
    assert content == [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "cG5nLWJ5dGVz",
            },
        },
        {"type": "text", "text": "Interpret this bounded figure crop."},
    ]


def test_anthropic_from_environment_does_not_export_unrelated_env_file_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ANTHROPIC_API_KEY=file-key\nPYTHONPATH=/tmp/untrusted\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    client = AnthropicHaikuClient.from_environment(env_path=env_path)

    assert client.api_key == "file-key"
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "PYTHONPATH" not in os.environ


def test_provider_helpers_classify_llm_providers():
    assert PROVIDER_CHOICES == ("deterministic", "anthropic", "claude-cli", "codex-cli", "host-agent")
    assert WORKER_PROVIDER_CHOICES == ("deterministic", "anthropic", "claude-cli", "codex-cli")
    assert is_llm_provider("anthropic")
    assert is_llm_provider("claude-cli")
    assert is_llm_provider("codex-cli")
    assert is_llm_provider("host-agent")
    assert not is_llm_provider("deterministic")
    assert not is_llm_provider("")
    assert llm_origin_for_provider("anthropic") == "anthropic-haiku"
    assert llm_origin_for_provider("claude-cli") == "claude-cli"
    assert llm_origin_for_provider("codex-cli") == "codex-cli"
    assert llm_origin_for_provider("host-agent") == "host-agent"
    assert resolve_provider_model("host-agent", DEFAULT_ANTHROPIC_MODEL) == ""


def test_resolve_provider_model_defaults_per_provider():
    assert resolve_provider_model("anthropic", "") == DEFAULT_ANTHROPIC_MODEL
    assert resolve_provider_model("anthropic", "custom-model") == "custom-model"
    assert resolve_provider_model("claude-cli", None) == DEFAULT_ANTHROPIC_MODEL
    assert resolve_provider_model("claude-cli", "claude-sonnet-5") == "claude-sonnet-5"
    assert resolve_provider_model("codex-cli", DEFAULT_ANTHROPIC_MODEL) == ""
    assert resolve_provider_model("codex-cli", "") == ""
    assert resolve_provider_model("codex-cli", "gpt-5-codex") == "gpt-5-codex"
    assert resolve_provider_model("deterministic", "anything") == ""


def test_claude_cli_client_runs_headless_print_mode_with_prompt_on_stdin():
    calls = []

    def runner(argv, stdin_text, timeout, env):
        calls.append((argv, stdin_text, timeout))
        return _completed(argv, stdout="  Generated hypothesis text.\n")

    client = ClaudeCLIClient(model="claude-haiku-4-5", binary="claude-test-bin", runner=runner)

    text = client.complete("Generate research ideas.", max_tokens=256)

    assert text == "Generated hypothesis text."
    argv, stdin_text, timeout = calls[0]
    assert argv == ["claude-test-bin", "-p", "--model", "claude-haiku-4-5", "--output-format", "text"]
    assert stdin_text == "Generate research ideas."
    assert timeout == pytest.approx(600.0)


def test_claude_cli_client_allowlists_child_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stale-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "stale-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://session-proxy.local")
    monkeypatch.setenv("DATABASE_PASSWORD", "do-not-leak")
    monkeypatch.setenv("UNRELATED_SERVICE_TOKEN", "do-not-leak")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/claude-config")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    seen_envs = []

    def runner(argv, stdin_text, timeout, env):
        seen_envs.append(env)
        return _completed(argv, stdout="ok")

    client = ClaudeCLIClient(binary="claude-test-bin", runner=runner)

    assert client.complete("prompt") == "ok"
    env = seen_envs[0]
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "DATABASE_PASSWORD" not in env
    assert "UNRELATED_SERVICE_TOKEN" not in env
    assert "PATH" in env
    assert env["CLAUDE_CONFIG_DIR"] == "/tmp/claude-config"
    assert env["LC_ALL"] == "C.UTF-8"


def test_claude_cli_client_resolves_alias_only_local_install(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    local_binary = fake_home / ".claude" / "local" / "claude"
    local_binary.parent.mkdir(parents=True)
    local_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("code_scientist.llm.shutil.which", lambda name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    resolved = ClaudeCLIClient(runner=lambda argv, stdin_text, timeout, env: _completed(argv))
    unresolved = ClaudeCLIClient(
        binary="/explicit/claude",
        runner=lambda argv, stdin_text, timeout, env: _completed(argv),
    )

    assert resolved.binary == str(local_binary)
    assert unresolved.binary == "/explicit/claude"


def test_claude_cli_client_wraps_nonzero_exit_as_request_error():
    def runner(argv, stdin_text, timeout, env):
        return _completed(argv, returncode=1, stderr="Not logged in.\nRun claude login first.")

    client = ClaudeCLIClient(binary="claude-test-bin", runner=runner)

    with pytest.raises(LLMRequestError, match="status 1.*Not logged in"):
        client.complete("prompt")


def test_claude_cli_client_empty_output_is_response_error():
    client = ClaudeCLIClient(
        binary="claude-test-bin",
        runner=lambda argv, stdin_text, timeout, env: _completed(argv, stdout="   \n"),
    )

    with pytest.raises(LLMResponseError, match="empty response"):
        client.complete("prompt")


def test_claude_cli_client_missing_binary_is_configuration_error():
    def runner(argv, stdin_text, timeout, env):
        raise FileNotFoundError(argv[0])

    client = ClaudeCLIClient(binary="claude-test-bin", runner=runner)

    with pytest.raises(LLMConfigurationError, match="'claude-test-bin' binary on PATH"):
        client.complete("prompt")


def test_claude_cli_client_timeout_is_request_error():
    def runner(argv, stdin_text, timeout, env):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    client = ClaudeCLIClient(binary="claude-test-bin", timeout=5, runner=runner)

    with pytest.raises(LLMRequestError, match="timed out after 5"):
        client.complete("prompt")


def test_claude_cli_client_rejects_multimodal_content():
    client = ClaudeCLIClient(
        binary="claude-test-bin",
        runner=lambda argv, stdin_text, timeout, env: _completed(argv, stdout="x"),
    )

    with pytest.raises(LLMRequestError, match="does not support image content"):
        client.complete_multimodal("prompt", [{"media_type": "image/png", "data": "cG5n"}])


def test_codex_cli_client_reads_last_message_file_and_cleans_up():
    calls = []
    seen_paths = []

    def runner(argv, stdin_text, timeout, env):
        calls.append((argv, stdin_text))
        output_path = Path(argv[argv.index("--output-last-message") + 1])
        seen_paths.append(output_path)
        output_path.write_text("Codex hypothesis answer.\n", encoding="utf-8")
        return _completed(argv, stdout="thinking logs...")

    client = CodexCLIClient(runner=runner)

    text = client.complete("Generate research ideas.")

    assert text == "Codex hypothesis answer."
    argv, stdin_text = calls[0]
    assert argv[:6] == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--output-last-message",
    ]
    assert argv[-1] == "-"
    assert "--model" not in argv
    assert stdin_text == "Generate research ideas."
    assert not seen_paths[0].exists()


def test_codex_cli_client_allowlists_child_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "do-not-leak")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")
    seen_envs = []

    def runner(argv, stdin_text, timeout, env):
        seen_envs.append(env)
        Path(argv[argv.index("--output-last-message") + 1]).write_text("ok", encoding="utf-8")
        return _completed(argv)

    assert CodexCLIClient(runner=runner).complete("prompt") == "ok"
    assert seen_envs[0]["CODEX_HOME"] == "/tmp/codex-home"
    assert "PATH" in seen_envs[0]
    assert "OPENAI_API_KEY" not in seen_envs[0]
    assert "GITHUB_TOKEN" not in seen_envs[0]


def test_codex_cli_client_forwards_explicit_model():
    seen_argv = []

    def runner(argv, stdin_text, timeout, env):
        seen_argv.append(argv)
        Path(argv[argv.index("--output-last-message") + 1]).write_text("ok", encoding="utf-8")
        return _completed(argv)

    client = CodexCLIClient(model="gpt-5-codex", runner=runner)

    assert client.complete("prompt") == "ok"
    argv = seen_argv[0]
    assert argv[argv.index("--model") + 1] == "gpt-5-codex"


def test_codex_cli_client_missing_output_is_response_error():
    client = CodexCLIClient(
        runner=lambda argv, stdin_text, timeout, env: _completed(argv, stdout="logs only"),
    )

    with pytest.raises(LLMResponseError, match="empty response"):
        client.complete("prompt")


def test_create_llm_client_builds_host_cli_clients():
    claude_client = create_llm_client("claude-cli", model="", runner=lambda *a: _completed([]))
    codex_default = create_llm_client("codex-cli", model=DEFAULT_ANTHROPIC_MODEL, runner=lambda *a: _completed([]))
    codex_explicit = create_llm_client("codex-cli", model="gpt-5-codex", runner=lambda *a: _completed([]))

    assert isinstance(claude_client, ClaudeCLIClient)
    assert claude_client.model == DEFAULT_ANTHROPIC_MODEL
    assert isinstance(codex_default, CodexCLIClient)
    assert codex_default.model == ""
    assert codex_explicit.model == "gpt-5-codex"


def test_create_llm_client_builds_anthropic_client_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("ANTHROPIC_API_KEY=file-key\n", encoding="utf-8")

    client = create_llm_client("anthropic", model="", env_file=env_path)

    assert isinstance(client, AnthropicHaikuClient)
    assert client.model == DEFAULT_ANTHROPIC_MODEL


def test_create_llm_client_rejects_unknown_provider():
    with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
        create_llm_client("deterministic")


def test_create_llm_client_host_agent_requires_bridge_dir(tmp_path):
    with pytest.raises(LLMConfigurationError, match="bridge directory"):
        create_llm_client("host-agent")

    client = create_llm_client("host-agent", bridge_dir=tmp_path / "llm-bridge")

    assert isinstance(client, HostAgentBridgeClient)
    assert client.requests_dir == tmp_path / "llm-bridge" / "requests"


def _bridge_responder(bridge_dir, build_response, stop):
    while not stop.is_set():
        requests_dir = bridge_dir / "requests"
        if requests_dir.exists():
            for request_path in sorted(requests_dir.glob("*.json")):
                try:
                    payload = json.loads(request_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                responses_dir = bridge_dir / "responses"
                responses_dir.mkdir(parents=True, exist_ok=True)
                (responses_dir / f"{payload['id']}.json").write_text(
                    json.dumps(build_response(payload)), encoding="utf-8"
                )
        time.sleep(0.01)


def _run_with_responder(bridge_dir, build_response, action):
    stop = threading.Event()
    thread = threading.Thread(
        target=_bridge_responder, args=(bridge_dir, build_response, stop), daemon=True
    )
    thread.start()
    try:
        return action()
    finally:
        stop.set()
        thread.join(timeout=2)


def test_host_agent_bridge_round_trip_consumes_request_and_strips_fence(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    seen_requests = []

    def build_response(payload):
        seen_requests.append(payload)
        return {"id": payload["id"], "response": "```json\n[\"idea\"]\n```"}

    client = HostAgentBridgeClient(bridge_dir, timeout=5, poll_seconds=0.01)

    text = _run_with_responder(
        bridge_dir, build_response, lambda: client.complete("Generate ideas.", max_tokens=321)
    )

    assert text == '["idea"]'
    assert seen_requests[0]["prompt"] == "Generate ideas."
    assert seen_requests[0]["max_tokens"] == 321
    assert list((bridge_dir / "requests").glob("*.json")) == []


def test_host_agent_bridge_error_response_is_request_error(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=5, poll_seconds=0.01)

    def act():
        with pytest.raises(LLMRequestError, match="cannot answer safely"):
            client.complete("prompt")

    _run_with_responder(
        bridge_dir,
        lambda payload: {"id": payload["id"], "error": "cannot answer safely"},
        act,
    )


def test_host_agent_bridge_blank_response_text_is_response_error(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=5, poll_seconds=0.01)

    def act():
        with pytest.raises(LLMResponseError, match="did not contain response text"):
            client.complete("prompt")

    _run_with_responder(
        bridge_dir,
        lambda payload: {"id": payload["id"], "response": "   "},
        act,
    )


def test_host_agent_bridge_times_out_and_removes_request(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=0.2, poll_seconds=0.02)

    with pytest.raises(LLMRequestError, match="did not answer bridge request"):
        client.complete("prompt")

    assert list((bridge_dir / "requests").glob("*.json")) == []


def test_host_agent_bridge_tolerates_partial_response_writes(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=5, poll_seconds=0.01)
    stop = threading.Event()

    def slow_responder():
        while not stop.is_set():
            requests_dir = bridge_dir / "requests"
            pending = sorted(requests_dir.glob("*.json")) if requests_dir.exists() else []
            for request_path in pending:
                try:
                    payload = json.loads(request_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                responses_dir = bridge_dir / "responses"
                responses_dir.mkdir(parents=True, exist_ok=True)
                response_path = responses_dir / f"{payload['id']}.json"
                response_path.write_text('{"id": "', encoding="utf-8")
                time.sleep(0.05)
                response_path.write_text(
                    json.dumps({"id": payload["id"], "response": "eventual answer"}),
                    encoding="utf-8",
                )
                return
            time.sleep(0.01)

    thread = threading.Thread(target=slow_responder, daemon=True)
    thread.start()
    try:
        assert client.complete("prompt") == "eventual answer"
    finally:
        stop.set()
        thread.join(timeout=2)


def test_host_agent_bridge_rejects_multimodal_content(tmp_path):
    client = HostAgentBridgeClient(tmp_path / "llm-bridge")

    with pytest.raises(LLMRequestError, match="does not support image content"):
        client.complete_multimodal("prompt", [{"media_type": "image/png", "data": "cG5n"}])


def test_host_agent_bridge_stop_file_cancels_immediately(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    bridge_dir.mkdir(parents=True)
    (bridge_dir / "stop").write_text("", encoding="utf-8")
    client = HostAgentBridgeClient(bridge_dir, timeout=30, poll_seconds=0.01)

    started = time.monotonic()
    with pytest.raises(LLMRequestError, match="stop was requested"):
        client.complete("prompt")

    assert time.monotonic() - started < 5
    assert not (bridge_dir / "requests").exists() or not list((bridge_dir / "requests").glob("*.json"))


def test_host_agent_bridge_stop_file_aborts_in_flight_wait(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=30, poll_seconds=0.01)

    def stopper():
        time.sleep(0.1)
        bridge_dir.mkdir(parents=True, exist_ok=True)
        (bridge_dir / "stop").write_text("", encoding="utf-8")

    thread = threading.Thread(target=stopper, daemon=True)
    started = time.monotonic()
    thread.start()
    try:
        with pytest.raises(LLMRequestError, match="stop was requested"):
            client.complete("prompt")
    finally:
        thread.join(timeout=2)

    assert time.monotonic() - started < 5
    assert list((bridge_dir / "requests").glob("*.json")) == []


def test_host_agent_bridge_declares_abandonment_after_consecutive_timeouts(tmp_path):
    bridge_dir = tmp_path / "llm-bridge"
    client = HostAgentBridgeClient(bridge_dir, timeout=0.05, poll_seconds=0.01)

    for _attempt in range(2):
        with pytest.raises(LLMRequestError, match="did not answer"):
            client.complete("prompt")

    started = time.monotonic()
    with pytest.raises(LLMRequestError, match="appears abandoned"):
        client.complete("prompt")

    assert time.monotonic() - started < 0.05
    assert list((bridge_dir / "requests").glob("*.json")) == []


def test_budgeted_llm_client_caps_calls_and_proxies_attributes():
    class FakeLLM:
        model = "fake-model"

        def __init__(self):
            self.calls = 0

        def complete(self, prompt, max_tokens):
            self.calls += 1
            return "ok"

        def complete_multimodal(self, prompt, images, max_tokens):
            self.calls += 1
            return "ok-image"

    inner = FakeLLM()
    client = BudgetedLLMClient(inner, limit=2)

    assert client.complete("one", max_tokens=16) == "ok"
    assert client.complete_multimodal("two", [], max_tokens=16) == "ok-image"
    assert client.used == 2
    assert client.model == "fake-model"

    with pytest.raises(LLMRequestError, match="budget exhausted"):
        client.complete("three")

    assert inner.calls == 2
