"""Central settings, read once from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    chat_model: str
    embed_model: str
    embed_dim: int
    embed_provider: str

    top_k: int
    relevance_threshold: float

    chunk_tokens: int
    chunk_overlap_tokens: int

    temperature: float
    max_output_tokens: int
    max_context_tokens: int

    corpus_dir: Path
    storage_dir: Path
    collection_name: str

    @property
    def chroma_dir(self) -> Path:
        return self.storage_dir / "chroma"

    @property
    def embedding_cache_path(self) -> Path:
        return self.storage_dir / "embedding_cache.jsonl"

    @property
    def query_log_path(self) -> Path:
        return self.storage_dir / "query_log.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY", ""),
        chat_model=_env("CHAT_MODEL", "gemini-3.5-flash-lite"),
        embed_model=_env("EMBED_MODEL", "gemini-embedding-001"),
        embed_dim=int(_env("EMBED_DIM", "768")),
        embed_provider=_env("EMBED_PROVIDER", "gemini").lower(),
        top_k=int(_env("TOP_K", "5")),
        relevance_threshold=float(_env("RELEVANCE_THRESHOLD", "0.65")),
        chunk_tokens=int(_env("CHUNK_TOKENS", "350")),
        chunk_overlap_tokens=int(_env("CHUNK_OVERLAP_TOKENS", "50")),
        temperature=float(_env("TEMPERATURE", "0.1")),
        max_output_tokens=int(_env("MAX_OUTPUT_TOKENS", "1024")),
        max_context_tokens=int(_env("MAX_CONTEXT_TOKENS", "6000")),
        corpus_dir=Path(_env("CORPUS_DIR", str(ROOT_DIR / "data" / "corpus"))),
        storage_dir=Path(_env("STORAGE_DIR", str(ROOT_DIR / "storage"))),
        collection_name=_env("COLLECTION_NAME", "telecom_docs"),
    )
