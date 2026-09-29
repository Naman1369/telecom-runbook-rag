# Team workflow

## Branches

- `main` is always deployable. No direct pushes; changes go through a PR with one teammate's approval.
- Feature branches: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`
  (e.g. `feat/pdf-loader`, `fix/version-detect`).

## Flow

1. Pick or create a GitHub issue and assign yourself.
2. `git checkout main && git pull`, then `git checkout -b feat/<name>`.
3. Commit small, focused changes: `feat: add pdf sidecar metadata`, `fix: ...`, `docs: ...`, `test: ...`.
4. Run `pytest` locally before pushing (it is offline and takes about 3 s).
5. `git push -u origin feat/<name>` and open a PR using the template. Link the issue (`Closes #12`).
6. A teammate reviews and approves, then squash-merges.

## Never commit

- `.env` or any API key. If a key is ever pushed, **revoke it in Google AI Studio immediately**.
- `storage/` (generated index, cache and logs). Rebuild it with `python scripts/ingest.py`.

## Work split (3 members)

| Member | Ownership | Roadmap items |
| --- | --- | --- |
| Naman Binu | Ingestion: loaders, cleaning, chunking, corpus validation, adding more docs | 3.3, 3.19 – 3.24 |
| Shubham Padkonde | Embeddings, vector store, retrieval tuning (threshold, top-k), evaluation | 3.4, 3.5, 3.25 – 3.32 |
| Akash Kolhe | LLM layer, prompts, RAG pipeline, API, web UI, deployment | 3.12 – 3.18, 3.6, 3.7 |
| Everyone | PRD, mock UX, README, demo | 3.1, 3.8, 3.9, 3.11 |

## Suggested issues to open

1. Add more real-world-style runbooks (fibre cut, power outage, microwave link fade).
2. Tune `RELEVANCE_THRESHOLD` using `scripts/evaluate.py` results.
3. Add a feedback button (👍/👎) per answer and log it.
4. Deploy to Render (see `render.yaml`).
5. Add a PDF vendor manual to the sample corpus.
