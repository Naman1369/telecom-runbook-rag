"""Embedding providers with batching, retry/backoff, a content-hash cache and cost tracking.

- ``GeminiEmbedder`` — production path (``gemini-embedding-001``), asymmetric task types for
  documents vs. queries, vectors L2-normalised so cosine similarity is a dot product.
- ``LocalHashEmbedder`` — deterministic offline embedder (hashed word unigrams + bigrams).
  Used by the test-suite and for demos without an API key. It captures keyword overlap only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings
from app.tokens import estimate_cost, estimate_tokens

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass
class EmbeddingStats:
    api_calls: int = 0
    embedded: int = 0
    cache_hits: int = 0
    retries: int = 0
    input_tokens: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


class Embedder(Protocol):
    name: str
    dim: int
    stats: EmbeddingStats

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingCache:
    """Append-only JSONL cache keyed by sha256(model | dim | task | text) — no duplicate API work."""

    def __init__(self, path: Path | None):
        self.path = path
        self._data: dict[str, list[float]] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._data[row["k"]] = row["v"]

    @staticmethod
    def key(model: str, dim: int, task: str, text: str) -> str:
        return hashlib.sha256(f"{model}|{dim}|{task}|{text}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> list[float] | None:
        return self._data.get(key)

    def put_many(self, items: dict[str, list[float]]) -> None:
        self._data.update(items)
        if self.path and items:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                for k, v in items.items():
                    fh.write(json.dumps({"k": k, "v": v}) + "\n")


class GeminiEmbedder:
    def __init__(self, settings: Settings, cache: EmbeddingCache | None = None,
                 batch_size: int = 50, max_retries: int = 5):
        from google import genai

        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set — copy .env.example to .env and add your key.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.embed_model
        self.dim = settings.embed_dim
        self.name = f"gemini:{self.model}:{self.dim}"
        self.cache = cache or EmbeddingCache(None)
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.stats = EmbeddingStats()

    def _call(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import errors, types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                self.stats.api_calls += 1
                response = self.client.models.embed_content(model=self.model, contents=texts, config=config)
                return [l2_normalize(list(e.values)) for e in response.embeddings]
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS or attempt == self.max_retries:
                    raise
                self.stats.retries += 1
                log.warning("Embedding API %s — retry %d in %.0fs", exc.code, attempt + 1, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError("unreachable")

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        keys = [EmbeddingCache.key(self.model, self.dim, task_type, t) for t in texts]
        results: list[list[float] | None] = [self.cache.get(k) for k in keys]
        self.stats.cache_hits += sum(r is not None for r in results)

        # De-duplicate identical texts inside the same run as well.
        pending: dict[str, int] = {}
        for i, (k, r) in enumerate(zip(keys, results)):
            if r is None and k not in pending:
                pending[k] = i
        todo = list(pending.items())

        for start in range(0, len(todo), self.batch_size):
            batch = todo[start:start + self.batch_size]
            batch_texts = [texts[i] for _, i in batch]
            vectors = self._call(batch_texts, task_type)
            tokens = sum(estimate_tokens(t) for t in batch_texts)
            self.stats.embedded += len(batch)
            self.stats.input_tokens += tokens
            self.stats.cost_usd += estimate_cost(self.model, tokens)
            self.cache.put_many({k: v for (k, _), v in zip(batch, vectors)})

        return [r if r is not None else self.cache.get(k) for k, r in zip(keys, results)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-./]*")


class LocalHashEmbedder:
    """Offline fallback: feature-hashed bag of unigrams + bigrams. Deterministic, no network."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.name = f"local-hash:{dim}"
        self.stats = EmbeddingStats()

    def _vector(self, text: str) -> list[float]:
        words = _TOKEN.findall(text.lower())
        features = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
        vec = [0.0] * self.dim
        for feat in features:
            h = int.from_bytes(hashlib.md5(feat.encode("utf-8")).digest()[:8], "little")
            vec[h % self.dim] += 1.0 if (h >> 63) == 0 else -1.0
        return l2_normalize(vec)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.stats.embedded += len(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def get_embedder(settings: Settings | None = None, use_cache: bool = True) -> Embedder:
    settings = settings or get_settings()
    if settings.embed_provider == "local":
        return LocalHashEmbedder(settings.embed_dim)
    cache = EmbeddingCache(settings.embedding_cache_path if use_cache else None)
    return GeminiEmbedder(settings, cache=cache)
