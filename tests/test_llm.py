import os

import pytest

from code_scientist.llm import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicHaikuClient,
    LLMConfigurationError,
    LLMRequestError,
    load_dotenv,
)


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
