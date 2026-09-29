"""FastAPI service: JSON API + static web app (query box, answer view, source panel)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import ROOT_DIR, get_settings
from app.embeddings import get_embedder
from app.llm import GeminiChat, LLMError
from app.rag import QueryError, QueryRequest, RAGPipeline
from app.vectorstore import VectorStore, read_catalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEB_DIR = ROOT_DIR / "web"

app = FastAPI(title="NOC Copilot — Telecom Runbook RAG", version="1.0.0")


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class QueryBody(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    product: str | None = None
    version: str | None = None
    doc_types: list[str] | None = None
    history: list[Turn] = Field(default_factory=list, max_length=20)


@lru_cache(maxsize=1)
def get_pipeline() -> RAGPipeline:
    settings = get_settings()
    store = VectorStore(settings)
    if not store.exists():
        raise RuntimeError("The vector index is empty — run `python scripts/ingest.py` first.")
    return RAGPipeline(get_embedder(settings), store, GeminiChat(settings), settings)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    store = VectorStore(settings)
    indexed = store.count() if store.exists() else 0
    return {
        "status": "ok" if indexed else "no_index",
        "indexed_chunks": indexed,
        "chat_model": settings.chat_model,
        "embed_model": settings.embed_model if settings.embed_provider == "gemini" else "local-hash",
        "api_key_configured": bool(settings.gemini_api_key),
    }


@app.get("/api/catalog")
def catalog() -> dict:
    return read_catalog()


@app.post("/api/query")
def query(body: QueryBody) -> dict:
    try:
        pipeline = get_pipeline()
    except (RuntimeError, LLMError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    req = QueryRequest(
        question=body.question,
        product=body.product or None,
        version=body.version or None,
        doc_types=body.doc_types or None,
        history=[t.model_dump() for t in body.history],
    )
    try:
        return pipeline.answer(req)
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=Path(WEB_DIR)), name="static")
