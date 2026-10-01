import httpx
import pytest
from pydantic import BaseModel

from app.llm import GeminiChat, LLMError


class Reply(BaseModel):
    ok: bool


class _Usage:
    prompt_token_count = 10
    candidates_token_count = 5
    thoughts_token_count = 0


class _Response:
    usage_metadata = _Usage()
    parsed = Reply(ok=True)
    text = '{"ok": true}'


def chat(behaviour):
    """GeminiChat with the network call replaced by ``behaviour(model)``."""
    instance = GeminiChat.__new__(GeminiChat)
    instance.models = ["primary", "backup"]
    instance.model = "primary"
    instance.timeout_seconds = 10.0
    instance.calls = []
    instance._config = lambda system, schema: None

    def generate(model, prompt, config):
        instance.calls.append(model)
        return behaviour(model)

    instance._generate = generate
    return instance


def test_timeout_on_primary_falls_back_to_next_model():
    def behaviour(model):
        if model == "primary":
            raise httpx.ReadTimeout("stalled")
        return _Response()

    instance = chat(behaviour)
    parsed, usage = instance.generate_json("system", "prompt", Reply)
    assert parsed.ok is True
    assert instance.calls == ["primary", "backup"]
    assert usage.model == "backup"


def test_timeout_on_every_model_raises_a_clear_error():
    def behaviour(model):
        raise httpx.ConnectTimeout("stalled")

    instance = chat(behaviour)
    with pytest.raises(LLMError, match="did not respond within 10 s"):
        instance.generate_json("system", "prompt", Reply)
    assert instance.calls == ["primary", "backup"]
