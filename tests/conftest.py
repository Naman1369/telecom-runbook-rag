import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.embeddings import LocalHashEmbedder  # noqa: E402
from app.llm import LLMUsage  # noqa: E402
from app.vectorstore import VectorStore  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    """Offline settings: local hashing embedder, isolated storage directory."""
    return dataclasses.replace(
        get_settings(),
        storage_dir=tmp_path / "storage",
        embed_provider="local",
        relevance_threshold=0.05,
        gemini_api_key="",
    )


@pytest.fixture
def indexed(settings):
    """Run the real ingestion pipeline over data/corpus into a temp Chroma index."""
    from app.ingest.pipeline import run_ingestion

    embedder = LocalHashEmbedder(settings.embed_dim)
    store = VectorStore(settings)
    report = run_ingestion(settings, embedder=embedder, store=store, skip_quality=True)
    return settings, embedder, store, report


class FakeLLM:
    """Stands in for Gemini: returns a canned structured answer and records the prompt."""

    model = "fake-llm"

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def generate_json(self, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt})
        return schema.model_validate(self.answer), LLMUsage(input_tokens=100, output_tokens=50)
