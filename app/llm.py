"""Gemini chat client: structured (JSON-schema) output, tuned parameters, retries, usage tracking."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
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
    model: str = ""


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    model: str

    def generate_json(self, system: str, prompt: str, schema: type[T]) -> tuple[T, LLMUsage]: ...


class GeminiChat:
    """Primary model with ordered fallbacks: overloaded (503) or rate-limited (429) models are
    retried briefly, then the next model in ``CHAT_FALLBACK_MODELS`` is tried. A model that does
    not respond within ``CHAT_TIMEOUT_SECONDS`` (or returns 504, Google's own timeout) is skipped
    without a retry, because retrying it would make the engineer wait twice."""

    def __init__(self, settings: Settings | None = None, max_retries: int = 1):
        from google import genai
        from google.genai import types

        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set — copy .env.example to .env and add your key.")
        self.timeout_seconds = float(os.getenv("CHAT_TIMEOUT_SECONDS", "10"))
        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
        )
        self.model = self.settings.chat_model
        fallbacks = [m.strip() for m in os.getenv("CHAT_FALLBACK_MODELS", "gemini-3.1-flash-lite").split(",")]
        self.models = [self.model] + [m for m in fallbacks if m and m != self.model]
        self.max_retries = max_retries
        # Optional: Gemini 3.x takes a thinking *level* ("low", "high"); leave unset to use the model default.
        self.thinking_level = os.getenv("THINKING_LEVEL", "").strip()

    def _config(self, system: str, schema: type[BaseModel]):
        from google.genai import types

        kwargs = dict(
            system_instruction=system,
            temperature=self.settings.temperature,
            max_output_tokens=self.settings.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if self.thinking_level:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)
        return types.GenerateContentConfig(**kwargs)

    def _generate(self, model: str, prompt: str, config):
        from google.genai import errors

        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.models.generate_content(model=model, contents=prompt, config=config)
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS or exc.code == 504 or attempt == self.max_retries:
                    raise
                log.warning("%s returned %s — retry %d in %.0fs", model, exc.code, attempt + 1, delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    def generate_json(self, system: str, prompt: str, schema: type[T]) -> tuple[T, LLMUsage]:
        from google.genai import errors

        config = self._config(system, schema)
        response, used_model, last_error = None, None, None
        for model in self.models:
            try:
                response, used_model = self._generate(model, prompt, config), model
                break
            except errors.APIError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_STATUS:
                    break
                log.warning("%s unavailable (%s) — falling back", model, exc.code)
            except httpx.TransportError as exc:  # timeout or dropped connection
                last_error = exc
                log.warning("%s did not respond (%s) — falling back", model, type(exc).__name__)
        if response is None:
            if isinstance(last_error, httpx.TransportError):
                raise LLMError(f"Gemini did not respond within {self.timeout_seconds:g} s. "
                               "Please try again.") from last_error
            raise LLMError(f"Gemini API error {last_error.code}: {last_error.message}") from last_error

        meta = response.usage_metadata
        usage = LLMUsage(
            input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            output_tokens=(getattr(meta, "candidates_token_count", 0) or 0)
            + (getattr(meta, "thoughts_token_count", 0) or 0),
            model=used_model,
        )
        usage.cost_usd = estimate_cost(used_model, usage.input_tokens, usage.output_tokens)

        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed, usage
        try:
            return schema.model_validate(json.loads(response.text or "")), usage
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc
