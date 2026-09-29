"""Workflow 1 end-to-end: load → clean → chunk + tag → validate → embed → quality-check → index."""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import ROOT_DIR, Settings, get_settings
from app.embeddings import Embedder, cosine_similarity, get_embedder
from app.ingest.chunking import Chunk, chunk_document
from app.ingest.cleaning import clean_text
from app.ingest.loaders import DOC_TYPES, Document, load_corpus
from app.vectorstore import VectorStore, write_catalog

log = logging.getLogger(__name__)

REQUIRED_METADATA = ("vendor", "product", "version", "doc_type", "title", "section", "chunk_id")
PROBES_PATH = ROOT_DIR / "eval" / "embedding_probes.json"


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    indexed: int = 0
    load_errors: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    per_version: dict = field(default_factory=dict)
    token_stats: dict = field(default_factory=dict)
    embedding: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.validation_errors and self.indexed == self.chunks and self.quality.get("passed", True)


# --- step 4: corpus validation (risk: inconsistent legacy metadata) ------------------------

def validate_corpus(documents: list[Document], chunks: list[Chunk], max_tokens: int) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    chunked_docs = {c.doc.doc_id for c in chunks}
    for doc in documents:
        if not doc.text.strip():
            errors.append(f"{doc.doc_id}: no text extracted")
        elif doc.doc_id not in chunked_docs:
            errors.append(f"{doc.doc_id}: produced zero chunks")
        if doc.doc_type not in DOC_TYPES:
            errors.append(f"{doc.doc_id}: invalid doc_type {doc.doc_type}")
        if not doc.url:
            warnings.append(f"{doc.doc_id}: no source URL in metadata")

    seen_ids: set[str] = set()
    hashes: Counter = Counter()
    for chunk in chunks:
        meta = chunk.metadata()
        missing = [k for k in REQUIRED_METADATA if not str(meta.get(k, "")).strip()]
        if missing:
            errors.append(f"{chunk.chunk_id}: missing metadata {missing}")
        if chunk.chunk_id in seen_ids:
            errors.append(f"{chunk.chunk_id}: duplicate chunk id")
        seen_ids.add(chunk.chunk_id)
        if chunk.token_count > max_tokens * 1.1:
            warnings.append(f"{chunk.chunk_id}: {chunk.token_count} tokens exceeds limit {max_tokens}")
        hashes[(chunk.doc.product, chunk.doc.version, chunk.content_hash)] += 1

    for (product, version, _), n in hashes.items():
        if n > 1:
            warnings.append(f"{product} {version}: {n} chunks with identical text")

    versions = {(d.product, d.version) for d in documents}
    for product, version in sorted(versions):
        types = {d.doc_type for d in documents if (d.product, d.version) == (product, version)}
        if "runbook" not in types:
            warnings.append(f"{product} {version}: no troubleshooting runbook ingested")
    return errors, warnings


# --- step 6: embedding quality checks ------------------------------------------------------

def quality_check(embedder: Embedder, chunks: list[Chunk], vectors: list[list[float]]) -> dict:
    result: dict = {"probes": [], "passed": True}

    if PROBES_PATH.exists():
        probes = json.loads(PROBES_PATH.read_text(encoding="utf-8"))
        texts = [t for p in probes for t in (p["anchor"], p["related"], p["unrelated"])]
        vecs = embedder.embed_documents(texts)
        passed = 0
        for i, probe in enumerate(probes):
            a, r, u = vecs[3 * i: 3 * i + 3]
            sim_r, sim_u = cosine_similarity(a, r), cosine_similarity(a, u)
            ok = sim_r > sim_u
            passed += ok
            result["probes"].append({"anchor": probe["anchor"], "related": round(sim_r, 3),
                                     "unrelated": round(sim_u, 3), "ok": ok})
        result["probe_pass_rate"] = round(passed / len(probes), 3) if probes else None
        result["passed"] = passed == len(probes)

    # Nearest neighbour of each chunk should usually come from the same product family.
    same_product = 0
    for i, vi in enumerate(vectors):
        best_j, best = -1, -2.0
        for j, vj in enumerate(vectors):
            if i != j:
                s = sum(x * y for x, y in zip(vi, vj))  # vectors are L2-normalised
                if s > best:
                    best_j, best = j, s
        same_product += chunks[best_j].doc.product == chunks[i].doc.product
    result["nearest_neighbour_same_product"] = round(same_product / len(vectors), 3) if vectors else None
    return result


# --- orchestration --------------------------------------------------------------------------

def build_chunks(settings: Settings) -> tuple[list[Document], list[Chunk], list[str]]:
    documents, load_errors = load_corpus(settings.corpus_dir)
    chunks: list[Chunk] = []
    for doc in documents:
        doc.text = clean_text(doc.text)
        chunks.extend(chunk_document(doc, settings.chunk_tokens, settings.chunk_overlap_tokens))
    return documents, chunks, load_errors


def run_ingestion(settings: Settings | None = None, embedder: Embedder | None = None,
                  store: VectorStore | None = None, skip_quality: bool = False) -> IngestReport:
    settings = settings or get_settings()
    started = time.perf_counter()
    report = IngestReport()

    # 1–4. load, clean, chunk + tag
    documents, chunks, report.load_errors = build_chunks(settings)
    report.documents, report.chunks = len(documents), len(chunks)
    for c in chunks:
        key = f"{c.doc.product} {c.doc.version}"
        report.per_version[key] = report.per_version.get(key, 0) + 1
    sizes = sorted(c.token_count for c in chunks)
    if sizes:
        report.token_stats = {"min": sizes[0], "median": sizes[len(sizes) // 2], "max": sizes[-1],
                              "total": sum(sizes)}

    report.validation_errors, report.validation_warnings = validate_corpus(documents, chunks, settings.chunk_tokens)
    if report.validation_errors:
        log.error("Corpus validation failed — not indexing. %d errors", len(report.validation_errors))
        report.seconds = round(time.perf_counter() - started, 2)
        return report

    # 5. embed
    embedder = embedder or get_embedder(settings)
    vectors = embedder.embed_documents([c.embed_text for c in chunks])
    report.embedding = {"model": embedder.name, "dim": embedder.dim, **asdict(embedder.stats)}
    report.embedding["cost_usd"] = round(report.embedding["cost_usd"], 6)

    # 6. quality checks
    if not skip_quality:
        report.quality = quality_check(embedder, chunks, vectors)

    # 7. index + verify record counts
    store = store or VectorStore(settings)
    store.reset(embedder.name, embedder.dim)
    store.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=vectors,
        documents=[c.text for c in chunks],
        metadatas=[c.metadata() for c in chunks],
    )
    report.indexed = store.count()
    write_catalog([c.metadata() for c in chunks], settings)

    report.seconds = round(time.perf_counter() - started, 2)
    _write_report(report, settings.storage_dir / "ingest_report.json")
    return report


def _write_report(report: IngestReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    data["ok"] = report.ok
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
