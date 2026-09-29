"""Workflow 2 — version-scoped query & grounded answer.

capture query + version → embed query → version-filtered top-k → assemble context →
grounded JSON answer → attach citations → return + log.  If nothing relevant exists for the
requested release, the pipeline says so instead of guessing (no LLM call is made).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.embeddings import Embedder
from app.llm import ChatModel, LLMError
from app.prompts import render
from app.tokens import estimate_tokens, trim_to_tokens
from app.vectorstore import RetrievedChunk, VectorStore, read_catalog

HISTORY_TOKENS = 600
HISTORY_TURNS = 6


# --- structured output schema -----------------------------------------------------------------

class AnswerStep(BaseModel):
    instruction: str = Field(description="One short imperative step")
    command: str | None = Field(default=None, description="Exact CLI command from the excerpt, or null")
    sources: list[str] = Field(description="Excerpt labels supporting this step, e.g. ['S1']")


class LLMAnswer(BaseModel):
    answer_found: bool
    summary: str = Field(description="One or two sentences: what is wrong and the fix")
    steps: list[AnswerStep]
    warnings: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)


# --- request ----------------------------------------------------------------------------------

@dataclass
class QueryRequest:
    question: str
    product: str | None = None
    version: str | None = None
    vendor: str | None = None
    doc_types: list[str] | None = None
    history: list[dict] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]
    top_k: int | None = None


class QueryError(ValueError):
    pass


# --- step 1: resolve the target release -----------------------------------------------------

def detect_release(question: str, catalog: dict, product: str | None = None) -> tuple[str, str] | None:
    """Find a product/version mentioned in the question text, e.g. 'on AuroraOS 8.1'."""
    matches = set()
    for p in catalog.get("products", []):
        if product and p["product"] != product:
            continue
        for v in p["versions"]:
            if re.search(rf"(?<![\d.]){re.escape(v['version'])}(?![\d])", question):
                matches.add((p["product"], v["version"]))
    return matches.pop() if len(matches) == 1 else None


def resolve_release(req: QueryRequest, catalog: dict) -> tuple[str, str, str, bool]:
    detected = False
    product, version = req.product, req.version
    if not version:
        found = detect_release(req.question, catalog, product)
        if not found:
            raise QueryError("Select the product version — it could not be detected from the question.")
        product, version = found
        detected = True
    for p in catalog.get("products", []):
        if (product is None or p["product"] == product) and any(v["version"] == version for v in p["versions"]):
            return p["vendor"], p["product"], version, detected
    raise QueryError(f"No documentation is indexed for {product or 'any product'} version {version}.")


# --- step 4: context window management --------------------------------------------------------

def label(i: int) -> str:
    return f"S{i + 1}"


def build_context(chunks: list[RetrievedChunk], max_tokens: int) -> tuple[str, list[RetrievedChunk]]:
    parts, used, budget = [], [], max_tokens
    for i, chunk in enumerate(chunks):
        m = chunk.metadata
        header = f"[{label(i)}] {m['title']} ({m['product']} {m['version']}) — {m['section']} — lines {m['line_start']}-{m['line_end']}"
        block = f"{header}\n{chunk.text}"
        cost = estimate_tokens(block)
        if cost > budget:
            if budget > 150:  # room for a meaningful partial excerpt
                parts.append(trim_to_tokens(block, budget))
                used.append(chunk)
            break
        parts.append(block)
        used.append(chunk)
        budget -= cost
    return "\n\n---\n\n".join(parts), used


def build_history(history: list[dict], max_tokens: int = HISTORY_TOKENS) -> str:
    """Keep the most recent turns verbatim; compress older ones to one line each."""
    if not history:
        return ""
    recent = history[-HISTORY_TURNS:]
    older = history[:-HISTORY_TURNS]
    lines = []
    if older:
        gist = "; ".join(trim_to_tokens(t["content"], 15) for t in older if t.get("role") == "user")
        lines.append(f"(Earlier in this incident the engineer asked about: {gist})")
    for turn in recent:
        who = "Engineer" if turn.get("role") == "user" else "Assistant"
        lines.append(f"{who}: {trim_to_tokens(turn.get('content', ''), 120)}")
    text = "\n".join(lines)
    while estimate_tokens(text) > max_tokens and len(lines) > 1:
        lines.pop(1 if older else 0)
        text = "\n".join(lines)
    return f"Conversation so far (for context only — cite excerpts, not this):\n{text}\n"


def retrieval_text(req: QueryRequest) -> str:
    """Short follow-ups ("what if that fails?") are expanded with the previous question."""
    previous = [t["content"] for t in req.history if t.get("role") == "user"]
    if previous and len(req.question.split()) < 12:
        return f"{previous[-1]}\n{req.question}"
    return req.question


# --- orchestration ------------------------------------------------------------------------------

class RAGPipeline:
    def __init__(self, embedder: Embedder, store: VectorStore, llm: ChatModel | None,
                 settings: Settings | None = None):
        self.embedder = embedder
        self.store = store
        self.llm = llm
        self.settings = settings or get_settings()

    def answer(self, req: QueryRequest) -> dict:
        t0 = time.perf_counter()
        question = (req.question or "").strip()
        if not question:
            raise QueryError("Question is empty.")
        req.question = question[:2000]
        vendor, product, version, detected = resolve_release(req, read_catalog(self.settings))
        top_k = req.top_k or self.settings.top_k

        # 2. embed the query with the same model used at ingestion
        qvec = self.embedder.embed_query(retrieval_text(req))
        t_embed = time.perf_counter()

        # 3. version-filtered retrieval — the hard filter runs inside the vector search
        where = VectorStore.build_filter(version=version, product=product, vendor=vendor, doc_types=req.doc_types)
        retrieved = self.store.query(qvec, top_k, where)
        t_retrieve = time.perf_counter()

        relevant = [c for c in retrieved if c.score >= self.settings.relevance_threshold]
        base = {
            "question": req.question,
            "vendor": vendor,
            "product": product,
            "version": version,
            "version_detected": detected,
            "retrieved": [
                {"chunk_id": c.chunk_id, "score": round(c.score, 3), "section": c.metadata["section"],
                 "title": c.metadata["title"], "version": c.metadata["version"]}
                for c in retrieved
            ],
        }

        if not relevant:
            result = self._not_found(base, f"No section of the {product} {version} documentation is relevant "
                                           "enough to answer this. Check the release, rephrase with the alarm "
                                           "name, or escalate to the vendor TAC.")
            return self._finish(result, t0, t_embed, t_retrieve, None)

        # 4. assemble context within the token budget
        context, used = build_context(relevant, self.settings.max_context_tokens)

        # 5. grounded generation (structured JSON)
        system = render("system", vendor=vendor, product=product, version=version)
        prompt = render("answer", history=build_history(req.history), product=product, version=version,
                        context=context, question=req.question)
        if self.llm is None:
            raise LLMError("No chat model configured.")
        parsed, usage = self.llm.generate_json(system, prompt, LLMAnswer)
        t_generate = time.perf_counter()

        # 6. attach citations — keep only labels that point at excerpts we actually supplied
        result = self._cite(base, parsed, used)
        result["usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                           "cost_usd": round(usage.cost_usd, 6), "model": usage.model or self.llm.model}
        return self._finish(result, t0, t_embed, t_retrieve, t_generate)

    # -----------------------------------------------------------------------------------------

    @staticmethod
    def _not_found(base: dict, reason: str) -> dict:
        return {**base, "status": "not_found", "summary": reason, "steps": [], "warnings": [], "citations": []}

    def _cite(self, base: dict, parsed: LLMAnswer, used: list[RetrievedChunk]) -> dict:
        index = {label(i): i for i in range(len(used))}
        cited: dict[str, int] = {}  # label -> citation number, in order of first use

        def refs(labels: list[str]) -> list[int]:
            out = []
            for raw in labels:
                lab = raw.strip().strip("[]").upper()
                if lab in index:
                    cited.setdefault(lab, len(cited) + 1)
                    out.append(cited[lab])
            return sorted(set(out))

        steps = []
        for step in parsed.steps:
            numbers = refs(step.sources)
            if numbers:  # drop any step the model could not ground in an excerpt
                steps.append({"instruction": step.instruction, "command": step.command, "citations": numbers})

        warnings = []
        for w in parsed.warnings:
            found = re.findall(r"\[(S\d+)\]", w)
            numbers = refs(found)
            text = re.sub(r"\s*\[S\d+\]", "", w).strip()
            warnings.append({"text": text, "citations": numbers})
        refs(parsed.sources_used)

        if not parsed.answer_found or not steps:
            reason = parsed.summary if not parsed.answer_found else (
                "The model could not ground an answer in the retrieved documentation.")
            return self._not_found(base, reason)

        citations = []
        for lab, number in sorted(cited.items(), key=lambda kv: kv[1]):
            chunk = used[index[lab]]
            m = chunk.metadata
            citations.append({
                "id": number,
                "title": m["title"],
                "section": m["section"],
                "vendor": m["vendor"],
                "product": m["product"],
                "version": m["version"],
                "doc_type": m["doc_type"],
                "url": m.get("url", ""),
                "source_path": m["source_path"],
                "line_start": m["line_start"],
                "line_end": m["line_end"],
                "score": round(chunk.score, 3),
                "snippet": chunk.text,
            })
        return {**base, "status": "answered", "summary": parsed.summary, "steps": steps,
                "warnings": warnings, "citations": citations}

    def _finish(self, result: dict, t0: float, t_embed: float, t_retrieve: float, t_generate: float | None) -> dict:
        end = time.perf_counter()
        result["latency_ms"] = {
            "embed": round((t_embed - t0) * 1000),
            "retrieve": round((t_retrieve - t_embed) * 1000),
            "generate": round((t_generate - t_retrieve) * 1000) if t_generate else 0,
            "total": round((end - t0) * 1000),
        }
        result.setdefault("usage", None)
        self._log(result)
        return result

    def _log(self, result: dict) -> None:
        path = self.settings.query_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": result["question"],
            "product": result["product"],
            "version": result["version"],
            "status": result["status"],
            "citations": [f"{c['source_path']}#L{c['line_start']}-{c['line_end']}" for c in result["citations"]],
            "latency_ms": result["latency_ms"]["total"],
            "usage": result.get("usage"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
