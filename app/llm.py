"""Gemini chat client: structured (JSON-schema) output, tuned parameters, retries, usage tracking."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.tokens import estimate_cost

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    model: str

    def generate_json(self, system: str, prompt: str, schema: type[T]) -> tuple[T, LLMUsage]: ...


class GeminiChat:
    def __init__(self, settings: Settings | None = None, max_retries: int = 2):
        from google import genai

        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set — copy .env.example to .env and add your key.")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)
        self.model = self.settings.chat_model
        self.max_retries = max_retries
        # 0 disables "thinking" on 2.5 Flash models, which keeps median latency under the 3 s target.
        self.thinking_budget = int(os.getenv("THINKING_BUDGET", "0"))

    def _config(self, system: str, schema: type[BaseModel]):
        from google.genai import types

        kwargs = dict(
            system_instruction=system,
            temperature=self.settings.temperature,
            max_output_tokens=self.settings.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
        )
        if self.thinking_budget >= 0:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self.thinking_budget)
        return types.GenerateContentConfig(**kwargs)

    def generate_json(self, system: str, prompt: str, schema: type[T]) -> tuple[T, LLMUsage]:
        from google.genai import errors

        config = self._config(system, schema)
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
                break
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS or attempt == self.max_retries:
                    raise LLMError(f"Gemini API error {exc.code}: {exc.message}") from exc
                log.warning("Chat API %s — retry %d in %.0fs", exc.code, attempt + 1, delay)
                time.sleep(delay)
                delay *= 2

        meta = response.usage_metadata
        usage = LLMUsage(
            input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            output_tokens=(getattr(meta, "candidates_token_count", 0) or 0)
            + (getattr(meta, "thoughts_token_count", 0) or 0),
        )
        usage.cost_usd = estimate_cost(self.model, usage.input_tokens, usage.output_tokens)

        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed, usage
        try:
            return schema.model_validate(json.loads(response.text or "")), usage
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc
