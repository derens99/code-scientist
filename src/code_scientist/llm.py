from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_CLAUDE_CLI_BINARY = "claude"
DEFAULT_CODEX_CLI_BINARY = "codex"
DEFAULT_CLI_TIMEOUT_SECONDS = 600.0
DEFAULT_BRIDGE_TIMEOUT_SECONDS = 600.0
DEFAULT_BRIDGE_POLL_SECONDS = 0.25
DEFAULT_BRIDGE_ABANDON_AFTER_TIMEOUTS = 2
BRIDGE_STOP_FILENAME = "stop"

LLM_PROVIDERS = ("anthropic", "claude-cli", "codex-cli", "host-agent")
PROVIDER_CHOICES = ("deterministic", *LLM_PROVIDERS)
# host-agent needs the live session that launched the run to answer its bridge
# requests, so detached worker processes cannot use it.
WORKER_PROVIDER_CHOICES = tuple(
    provider for provider in PROVIDER_CHOICES if provider != "host-agent"
)

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]
CommandRunner = Callable[
    [list[str], str, float, dict[str, str] | None], "subprocess.CompletedProcess[str]"
]

# Host CLIs should inherit only the operating-system and tool configuration they
# need. In particular, copying the ambient environment would expose unrelated
# repository/service credentials to every nested provider process.
HOST_CLI_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TERM",
        "COLORTERM",
        "NO_COLOR",
        "FORCE_COLOR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
    }
)


def host_cli_environment(explicit: dict[str, str] | None = None) -> dict[str, str]:
    """Build the minimal environment inherited by a local provider CLI.

    ``explicit`` is the sole escape hatch for provider inputs such as an API
    key deliberately loaded from a selected env file. Ambient values never
    become explicit implicitly.
    """

    env = {
        key: value
        for key, value in os.environ.items()
        if key in HOST_CLI_ENV_ALLOWLIST or key.startswith("LC_")
    }
    if explicit:
        env.update({str(key): str(value) for key, value in explicit.items()})
    return env


def is_llm_provider(provider: str) -> bool:
    return (provider or "").strip().lower() in LLM_PROVIDERS


def resolve_provider_model(provider: str, model: str | None) -> str:
    """Return the effective model string a provider runtime should advertise.

    The CLI defaults ``--model`` to the Anthropic model for every provider, so
    the codex-cli provider treats that default as "use the codex CLI's own
    configured model" rather than forwarding an Anthropic model id to codex.
    """

    normalized = (provider or "").strip().lower()
    requested = (model or "").strip()
    if normalized in {"anthropic", "claude-cli"}:
        return requested or DEFAULT_ANTHROPIC_MODEL
    if normalized == "codex-cli":
        return "" if requested == DEFAULT_ANTHROPIC_MODEL else requested
    return ""


def llm_origin_for_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized == "anthropic":
        return "anthropic-haiku"
    return normalized


class LLMConfigurationError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
    loaded = read_dotenv(path)
    for key, value in loaded.items():
        os.environ.setdefault(key, value)
    return loaded


def read_dotenv(path: str | Path = ".env") -> dict[str, str]:
    """Parse an env file without mutating the process environment."""

    env_path = Path(path)
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _parse_env_value(value)
        if not key:
            continue
        loaded[key] = value
    return loaded


class AnthropicHaikuClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        endpoint: str = ANTHROPIC_MESSAGES_ENDPOINT,
        transport: Transport | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is required for the Anthropic provider.")
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self._transport = transport or _urllib_transport

    @classmethod
    def from_environment(
        cls,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        env_path: str | Path = ".env",
        transport: Transport | None = None,
    ) -> AnthropicHaikuClient:
        file_values = read_dotenv(env_path)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "") or file_values.get(
            "ANTHROPIC_API_KEY", ""
        )
        if not api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is required for the Anthropic provider.")
        return cls(api_key=api_key, model=model, transport=transport)

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._complete_content(prompt, max_tokens=max_tokens)

    def complete_multimodal(
        self,
        prompt: str,
        images: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        content: list[dict[str, Any]] = []
        for image in images:
            media_type = str(image.get("media_type", ""))
            data = str(image.get("data", ""))
            if media_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
                raise ValueError(f"Unsupported image media type: {media_type}")
            if not data:
                raise ValueError("Multimodal image data is required")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
        content.append({"type": "text", "text": prompt})
        return self._complete_content(content, max_tokens=max_tokens)

    def _complete_content(self, content: str | list[dict[str, Any]], max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            response = self._transport(self.endpoint, headers, payload)
        except (LLMRequestError, LLMResponseError):
            raise
        except Exception as exc:
            raise LLMRequestError(f"Anthropic request failed: {exc.__class__.__name__}") from exc
        return _extract_text(response)


class _HostCLIClient:
    """Base for providers that answer completions through a local agent CLI.

    These providers reuse the host tool's existing login (Claude Code or Codex
    subscription auth), so no API key is required. Each completion spawns one
    headless CLI process; the CLI has no output-token cap flag, so
    ``max_tokens`` is accepted for interface compatibility and not enforced.
    """

    provider_label = "host-cli"

    def __init__(
        self,
        binary: str,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        runner: CommandRunner | None = None,
    ) -> None:
        if not binary:
            raise LLMConfigurationError(f"A CLI binary is required for the {self.provider_label} provider.")
        self.binary = binary
        self.timeout = float(timeout)
        self._runner = runner or _subprocess_runner

    def complete_multimodal(
        self,
        prompt: str,
        images: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        raise LLMRequestError(
            f"The {self.provider_label} provider does not support image content; "
            "PDF vision requires --provider anthropic."
        )

    def _run(
        self,
        argv: list[str],
        stdin_text: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._runner(argv, stdin_text, self.timeout, env)
        except FileNotFoundError as exc:
            raise LLMConfigurationError(
                f"The {self.provider_label} provider requires the '{self.binary}' binary on PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMRequestError(
                f"{self.provider_label} request timed out after {self.timeout:.0f} seconds."
            ) from exc
        except (LLMConfigurationError, LLMRequestError, LLMResponseError):
            raise
        except Exception as exc:
            raise LLMRequestError(
                f"{self.provider_label} request failed: {exc.__class__.__name__}"
            ) from exc
        if result.returncode != 0:
            detail = _tail_text(result.stderr) or _tail_text(result.stdout) or "no error output"
            raise LLMRequestError(
                f"{self.provider_label} exited with status {result.returncode}: {detail}"
            )
        return result


class ClaudeCLIClient(_HostCLIClient):
    """Completes prompts through headless Claude Code (`claude -p`)."""

    provider_label = "claude-cli"

    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        binary: str = DEFAULT_CLAUDE_CLI_BINARY,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        runner: CommandRunner | None = None,
    ) -> None:
        super().__init__(binary=_resolve_claude_binary(binary), timeout=timeout, runner=runner)
        self.model = (model or "").strip() or DEFAULT_ANTHROPIC_MODEL

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        argv = [self.binary, "-p", "--model", self.model, "--output-format", "text"]
        result = self._run(argv, prompt, env=host_cli_environment())
        text = result.stdout.strip()
        if not text:
            raise LLMResponseError("claude-cli returned an empty response.")
        return text


class CodexCLIClient(_HostCLIClient):
    """Completes prompts through non-interactive Codex (`codex exec`).

    An empty model means the codex CLI's own configured default model.
    """

    provider_label = "codex-cli"

    def __init__(
        self,
        model: str = "",
        binary: str = DEFAULT_CODEX_CLI_BINARY,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        runner: CommandRunner | None = None,
    ) -> None:
        super().__init__(binary=binary, timeout=timeout, runner=runner)
        self.model = (model or "").strip()

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        handle, raw_path = tempfile.mkstemp(prefix="code-scientist-codex-", suffix=".txt")
        os.close(handle)
        output_path = Path(raw_path)
        try:
            argv = [
                self.binary,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--output-last-message",
                str(output_path),
            ]
            if self.model:
                argv.extend(["--model", self.model])
            argv.append("-")
            self._run(argv, prompt, env=host_cli_environment())
            text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        finally:
            output_path.unlink(missing_ok=True)
        if not text:
            raise LLMResponseError("codex-cli returned an empty response.")
        return text


class HostAgentBridgeClient:
    """Blocks each completion on a file handshake with the host agent session.

    The engine writes ``<bridge_dir>/requests/<request-id>.json`` and waits for
    the session that launched the run (Claude Code, Codex, or any operator) to
    write ``<bridge_dir>/responses/<request-id>.json`` containing ``{"id",
    "response"}`` — so the host session and its subagents are the model. No API
    key or separate login is involved. A ``{"id", "error"}`` response fails the
    call; an unanswered request fails after ``timeout`` seconds.
    """

    def __init__(
        self,
        bridge_dir: str | Path,
        timeout: float | None = None,
        poll_seconds: float | None = None,
        abandon_after_timeouts: int = DEFAULT_BRIDGE_ABANDON_AFTER_TIMEOUTS,
    ) -> None:
        if not str(bridge_dir).strip():
            raise LLMConfigurationError("The host-agent provider requires a bridge directory.")
        self.bridge_dir = Path(bridge_dir)
        self.requests_dir = self.bridge_dir / "requests"
        self.responses_dir = self.bridge_dir / "responses"
        self.stop_path = self.bridge_dir / BRIDGE_STOP_FILENAME
        self.timeout = float(timeout if timeout is not None else DEFAULT_BRIDGE_TIMEOUT_SECONDS)
        self.poll_seconds = max(
            float(poll_seconds if poll_seconds is not None else DEFAULT_BRIDGE_POLL_SECONDS),
            0.01,
        )
        self.abandon_after_timeouts = max(int(abandon_after_timeouts), 1)
        self._counter = 0
        self._consecutive_timeouts = 0
        self._counter_lock = threading.Lock()

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self._raise_if_stopped()
        self._raise_if_abandoned()
        request_id = self._next_request_id()
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        request_path = self.requests_dir / f"{request_id}.json"
        _atomic_write_json(
            request_path,
            {
                "id": request_id,
                "prompt": prompt,
                "max_tokens": int(max_tokens),
                "created_at": time.time(),
            },
        )
        response_path = self.responses_dir / f"{request_id}.json"
        deadline = time.monotonic() + self.timeout
        while True:
            parsed = _read_json_object(response_path)
            if parsed is not None:
                request_path.unlink(missing_ok=True)
                with self._counter_lock:
                    self._consecutive_timeouts = 0
                error = str(parsed.get("error", "") or "").strip()
                if error:
                    raise LLMRequestError(
                        f"Host agent reported an error for bridge request {request_id}: {error}"
                    )
                response = parsed.get("response")
                if not isinstance(response, str) or not response.strip():
                    raise LLMResponseError(
                        f"Host agent bridge response {request_id} did not contain response text."
                    )
                return _strip_response_fence(response)
            if self.stop_path.exists():
                request_path.unlink(missing_ok=True)
                raise LLMRequestError(
                    f"Host agent bridge stop was requested ({self.stop_path}); "
                    f"bridge request {request_id} was cancelled."
                )
            if time.monotonic() >= deadline:
                request_path.unlink(missing_ok=True)
                with self._counter_lock:
                    self._consecutive_timeouts += 1
                raise LLMRequestError(
                    f"Host agent did not answer bridge request {request_id} "
                    f"within {self.timeout:.0f} seconds."
                )
            time.sleep(self.poll_seconds)

    def _raise_if_stopped(self) -> None:
        if self.stop_path.exists():
            raise LLMRequestError(
                f"Host agent bridge stop was requested ({self.stop_path}); "
                "no further bridge requests will be issued."
            )

    def _raise_if_abandoned(self) -> None:
        with self._counter_lock:
            timeouts = self._consecutive_timeouts
        if timeouts >= self.abandon_after_timeouts:
            raise LLMRequestError(
                f"Host agent bridge appears abandoned after {timeouts} consecutive "
                "unanswered requests; further bridge requests are disabled so the run "
                "can finish deterministically."
            )

    def complete_multimodal(
        self,
        prompt: str,
        images: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        raise LLMRequestError(
            "The host-agent provider does not support image content; "
            "PDF vision requires --provider anthropic."
        )

    def _next_request_id(self) -> str:
        with self._counter_lock:
            self._counter += 1
            sequence = self._counter
        return f"{time.time_ns()}-{os.getpid()}-{sequence:04d}"


class BudgetedLLMClient:
    """Hard cap on the number of completion calls a run may make.

    Exhaustion raises LLMRequestError, which agents already treat as a failed
    provider call, so the run degrades to its deterministic paths and finishes
    instead of spending further tokens.
    """

    def __init__(self, client: Any, limit: int) -> None:
        self._client = client
        self.limit = max(int(limit), 1)
        self._used = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self._consume()
        return self._client.complete(prompt, max_tokens=max_tokens)

    def complete_multimodal(
        self,
        prompt: str,
        images: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        self._consume()
        return self._client.complete_multimodal(prompt, images, max_tokens=max_tokens)

    def _consume(self) -> None:
        with self._lock:
            if self._used >= self.limit:
                raise LLMRequestError(
                    f"Provider call budget exhausted ({self.limit} calls); "
                    "further LLM calls are disabled for this run."
                )
            self._used += 1

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def create_llm_client(
    provider: str,
    model: str | None = None,
    env_file: str | Path = ".env",
    transport: Transport | None = None,
    runner: CommandRunner | None = None,
    bridge_dir: str | Path | None = None,
) -> Any:
    normalized = (provider or "").strip().lower()
    resolved_model = resolve_provider_model(normalized, model)
    if normalized == "anthropic":
        return AnthropicHaikuClient.from_environment(
            model=resolved_model or DEFAULT_ANTHROPIC_MODEL,
            env_path=env_file,
            transport=transport,
        )
    if normalized == "claude-cli":
        return ClaudeCLIClient(model=resolved_model, runner=runner)
    if normalized == "codex-cli":
        return CodexCLIClient(model=resolved_model, runner=runner)
    if normalized == "host-agent":
        if bridge_dir is None:
            raise LLMConfigurationError(
                "The host-agent provider requires a run bridge directory."
            )
        return HostAgentBridgeClient(bridge_dir)
    raise LLMConfigurationError(f"Unknown LLM provider: {provider}")


def _subprocess_runner(
    argv: list[str],
    stdin_text: str,
    timeout: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _resolve_claude_binary(binary: str) -> str:
    """Fall back to the `claude migrate-installer` location when the default
    binary is only reachable through a shell alias rather than PATH."""

    if binary != DEFAULT_CLAUDE_CLI_BINARY or shutil.which(binary):
        return binary
    fallback = Path.home() / ".claude" / "local" / "claude"
    if fallback.exists():
        return str(fallback)
    return binary


def _tail_text(text: str, limit: int = 400) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed[-limit:] if collapsed else ""


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, treating missing, partial, or non-object files as
    not-yet-written so bridge polling tolerates non-atomic host writers."""

    try:
        # ValueError subsumes both json.JSONDecodeError and the
        # UnicodeDecodeError a partial multibyte write raises; either means the
        # host has not finished writing this response yet.
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_response_fence(text: str) -> str:
    """Strip one Markdown code fence around a response.

    Handles the three shapes a host agent produces: a multi-line fenced block,
    a single-line ``` ```json{...}``` ``` block, and a fenced block followed by
    trailing prose. The opening fence consumes only an optional language tag
    (never the payload), and everything at and after the first closing fence is
    dropped so trailing commentary does not corrupt the JSON.
    """

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = re.sub(r"^```[A-Za-z0-9_.+-]*\n?", "", stripped)
    body = re.split(r"\n?```", body, maxsplit=1)[0]
    return body.strip()


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def _urllib_transport(endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise LLMRequestError(f"Anthropic request failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise LLMRequestError("Anthropic request failed due to a network error.") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("Anthropic response was not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise LLMResponseError("Anthropic response was not a JSON object.")
    return decoded


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("content")
    if not isinstance(content, list):
        raise LLMResponseError("Anthropic response did not include content blocks.")
    text_blocks = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    if not text_blocks:
        raise LLMResponseError("Anthropic response did not include text content.")
    return "\n".join(text_blocks)
