"""Token estimation and cost tracking.

Gemini's tokenizer is not available offline, so chunk sizing uses a character-based
estimate (~4 characters per token for English technical text). The estimate is only used
to keep chunks and prompts inside safe limits; billing-accurate counts come from the
`usage_metadata` returned by each API call.
"""

from __future__ import annotations

import math
import os

CHARS_PER_TOKEN = 4

# USD per 1M tokens — check https://ai.google.dev/pricing and fill in the model you use.
# Models missing here report a cost of 0 (unknown), unless CHAT_PRICE_INPUT/OUTPUT_PER_M are set.
PRICING_PER_MILLION = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-embedding-001": {"input": 0.15, "output": 0.0},
}


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    price = PRICING_PER_MILLION.get(model)
    if price is None and os.getenv("CHAT_PRICE_INPUT_PER_M"):
        price = {"input": float(os.getenv("CHAT_PRICE_INPUT_PER_M", "0")),
                 "output": float(os.getenv("CHAT_PRICE_OUTPUT_PER_M", "0"))}
    if price is None:
        return 0.0
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def trim_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN
    return text if len(text) <= max_chars else text[:max_chars].rsplit(" ", 1)[0] + " …"
