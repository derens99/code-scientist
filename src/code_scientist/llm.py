from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class LLMConfigurationError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
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
        os.environ.setdefault(key, value)
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
        load_dotenv(env_path)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is required for the Anthropic provider.")
        return cls(api_key=api_key, model=model, transport=transport)

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
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
