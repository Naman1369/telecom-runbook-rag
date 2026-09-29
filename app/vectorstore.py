"""Chroma vector store: HNSW (cosine) index with version/source metadata filtering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings, get_settings


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float  # cosine similarity in [-1, 1]
    metadata: dict


class VectorStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = chromadb.PersistentClient(
            path=str(self.settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.name = self.settings.collection_name

    # --- collection design -------------------------------------------------------------
    def reset(self, embedder_name: str, dim: int):
        try:
            self.client.delete_collection(self.name)
        except Exception:  # noqa: BLE001 — collection did not exist yet
            pass
        return self.client.create_collection(
            name=self.name,
            embedding_function=None,  # we always supply our own vectors
            configuration={"hnsw": {"space": "cosine", "ef_construction": 200, "max_neighbors": 16}},
            metadata={"embedder": embedder_name, "dim": dim},
        )

    @property
    def collection(self):
        return self.client.get_collection(self.name, embedding_function=None)

    def exists(self) -> bool:
        try:
            self.collection
            return True
        except Exception:  # noqa: BLE001
            return False

    # --- indexing ---------------------------------------------------------------------
    def add(self, ids: list[str], embeddings: list[list[float]], documents: list[str],
            metadatas: list[dict], batch_size: int = 200) -> None:
        col = self.collection
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            col.upsert(ids=ids[start:end], embeddings=embeddings[start:end],
                       documents=documents[start:end], metadatas=metadatas[start:end])

    def count(self) -> int:
        return self.collection.count()

    # --- retrieval --------------------------------------------------------------------
    @staticmethod
    def build_filter(version: str | None = None, product: str | None = None,
                     vendor: str | None = None, doc_types: list[str] | None = None) -> dict | None:
        clauses = []
        if vendor:
            clauses.append({"vendor": vendor})
        if product:
            clauses.append({"product": product})
        if version:
            clauses.append({"version": version})
        if doc_types:
            clauses.append({"doc_type": {"$in": doc_types}})
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def query(self, embedding: list[float], top_k: int, where: dict | None) -> list[RetrievedChunk]:
        res = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append(RetrievedChunk(chunk_id=cid, text=doc, score=1.0 - float(dist), metadata=meta))
        return out


# --- catalog (drives the product/version pickers in the UI) ------------------------------

def catalog_path(settings: Settings | None = None) -> Path:
    return (settings or get_settings()).storage_dir / "catalog.json"


def write_catalog(metadatas: list[dict], settings: Settings | None = None) -> dict:
    products: dict[str, dict] = {}
    for m in metadatas:
        p = products.setdefault(m["product"], {"vendor": m["vendor"], "product": m["product"], "versions": {}})
        v = p["versions"].setdefault(m["version"], {"documents": set(), "chunks": 0})
        v["documents"].add(m["title"])
        v["chunks"] += 1

    catalog = {"products": []}
    for product in sorted(products.values(), key=lambda p: (p["vendor"], p["product"])):
        catalog["products"].append({
            "vendor": product["vendor"],
            "product": product["product"],
            "versions": [
                {"version": ver, "documents": sorted(info["documents"]), "chunks": info["chunks"]}
                for ver, info in sorted(product["versions"].items(), key=lambda kv: _version_key(kv[0]))
            ],
        })
    path = catalog_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def read_catalog(settings: Settings | None = None) -> dict:
    path = catalog_path(settings)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"products": []}


def _version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in version.replace("-", ".").split("."))
