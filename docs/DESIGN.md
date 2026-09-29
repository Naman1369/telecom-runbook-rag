# Design notes

## Roadmap coverage

| Roadmap item | Where it lives |
| --- | --- |
| 3.2 / 3.10 Secure workspace, venv, `.env` | `.env.example`, `.gitignore`, `app/config.py` |
| 3.11 GitHub workflow | `docs/TEAM_WORKFLOW.md`, `.github/` templates |
| 3.12 LLM client + error handling | `app/llm.py` (retry on 429/5xx, `LLMError` → HTTP 502) |
| 3.13 Prompt construction | `app/prompts/system.md`: role, release scope, six grounding rules |
| 3.14 Tokens & cost | `app/tokens.py`, `usage` in every API response, ingest report cost |
| 3.15 Context window management | `build_context` (token budget), `build_history` (recent turns verbatim, older turns summarised) |
| 3.16 Model parameters | temperature 0.1, `max_output_tokens` 1024, thinking budget 0, all set in `.env` |
| 3.17 Structured output | `LLMAnswer` Pydantic schema passed as `response_schema`; re-validated on fallback |
| 3.18 Prompt templates | `.md` templates rendered with `string.Template` |
| 3.19 Multi-format intake | `app/ingest/loaders.py` (md, html, txt, pdf) |
| 3.20 Extraction & cleaning | `app/ingest/cleaning.py` |
| 3.21 Chunking strategies | section-aware strategy, see below |
| 3.22 Chunk metadata | `Chunk.metadata()`: vendor, product, version, doc_type, title, section, lines, url, hash |
| 3.23 Token-aware sizing & overlap | `CHUNK_TOKENS=350`, `CHUNK_OVERLAP_TOKENS=50` |
| 3.24 Corpus validation | `validate_corpus` blocks indexing on errors |
| 3.25–3.29 Embeddings | `app/embeddings.py`, `eval/embedding_probes.json`, quality section of ingest report |
| 3.30–3.32 Vector store | `app/vectorstore.py`: cosine HNSW, `$and` metadata filter, scores + metadata |
| 3.6 / 3.7 RAG + app | `app/rag.py`, `app/main.py`, `web/` |

## Chunking strategy comparison (3.21)

| Strategy | Pros | Cons for runbooks |
| --- | --- | --- |
| Fixed-size (N tokens) | Simple, uniform | Cuts procedures mid-list; step 4 ends up away from step 3 and its heading |
| Paragraph | Natural boundaries | Numbered steps are separate "paragraphs"; loses the procedure title |
| Recursive character | Good general default | Has no idea which heading a piece belongs to, so citations are vague |
| **Section-aware + token cap (chosen)** | Keeps a whole procedure (RB-101 … Resolution) together; section path gives exact citations | Needs headings; handled for html/txt/pdf by normalising to `#` headings |

Rules: a heading subtree that fits in 350 tokens is kept as one chunk. Larger sections are
split at sub-headings, then at paragraph or line boundaries, with 50 tokens of overlap. Bodies
under 40 tokens are merged into the next chunk rather than stored alone. The embedded text is
prefixed with `title | product version | doc_type | section` so the vector carries its context.

## Why the version filter goes inside the vector query

Filtering *after* top-k can return zero results when other releases' near-duplicate sections
fill the top k. Chroma applies the `where` clause during the HNSW search, so all k results are
from the requested release. We still re-check citation versions in the evaluation.

## Grounding safeguards

1. Relevance threshold (`RELEVANCE_THRESHOLD`, cosine). If nothing passes, return "not found"
   **without calling the LLM**.
2. The system prompt forbids anything outside the excerpts and requires S-labels per step.
3. The JSON schema forces `answer_found`, `steps[].sources`, `warnings`.
4. Post-validation drops any step whose sources are not among the supplied excerpts. If no step
   survives, the answer becomes "not found".

## Latency budget (< 3 s median)

The query embedding takes about 0.2–0.4 s, Chroma retrieval takes under 20 ms, and generation
on Flash with thinking disabled takes about 1–2 s. Retrieval context is capped at about 6k
tokens.
