# Team Overview: NOC Copilot

Start here. This page covers what we are building, how it works, how to run it, and what is
left before the **30 Sep 2026 (morning)** deadline. Details are in the linked docs.

Repo: https://github.com/Naman1369/telecom-runbook-rag  
Live app: https://noc-copilot.onrender.com

---

## 1. The project in one minute

**Problem (from our Sprint 2 statement).** A telecom operator has network configuration
guides, troubleshooting runbooks and vendor manuals, but support engineers cannot find the
exact resolution step during an outage, so recovery takes longer.

**Our answer: NOC Copilot**, a RAG (Retrieval-Augmented Generation) web app.

1. The engineer picks the **equipment** (e.g. AX-9000 router) and its **software release**
   (e.g. 8.1).
2. They type the symptom or alarm, e.g. *"BGP peer stuck in Idle, how do I reset it?"*
3. The app searches **only that release's documents**, gives the LLM the best matching
   sections, and shows:
   - numbered steps with **copyable CLI commands**
   - a **citation** on every step (document → section → line numbers)
   - warnings (service impact, escalation, known bugs)
4. If the docs for that release do not cover the question, it says **"no grounded answer"**
   instead of guessing.

**Why the release matters (our main selling point).** The same fix uses different commands
on different releases:

| Release | Reset a BGP session |
| --- | --- |
| AX-9000 **7.4** | `clear ip bgp 10.0.0.2 soft` |
| AX-9000 **8.1** | `reset bgp neighbor 10.0.0.2 soft` (the old command was removed) |

A normal chatbot or keyword search mixes these up. Our system tags every piece of
documentation with its release and **filters on it inside the search**, so the LLM never
sees the wrong release's docs.

---

## 2. Current status (29 Sep 2026)

| Area | Status |
| --- | --- |
| Repo, README, PRD, design notes, mock UX | ✅ Done |
| Ingestion pipeline (load → clean → chunk → validate → embed → index) | ✅ Done |
| Version-filtered retrieval (ChromaDB) | ✅ Done |
| Grounded answers with citations + "not found" fallback | ✅ Done |
| Web UI (query box, answer view, source panel) | ✅ Done |
| Tests: 84 offline tests | ✅ All passing |
| Evaluation: 21 golden questions | ✅ 21/21, see below |
| Deployment (Render, free plan) | ✅ Live at https://noc-copilot.onrender.com |
| Demo rehearsal | ⏳ **To do** |

**Evaluation results** (full details in [EVALUATION.md](EVALUATION.md)):

| Metric | Target | Result |
| --- | --- | --- |
| Correct source citation | ≥ 90% | **100%** |
| Scoped to the correct version | ≥ 95% | **100%** |
| Median response time | < 3 s | **1.29 s** on 29 Sep; 5.1 s on the 30 Sep re-run (Gemini slower that evening, see EVALUATION.md) |

---

## 3. How it works (plain language)

There are two halves, as described in the problem-statement PDF:

**A. Ingestion (run once, offline): `python scripts/ingest.py`**

```
docs in data/corpus/<vendor>/<product>/<version>/
  → load  (Markdown, HTML, TXT, PDF → text)
  → clean (remove menus, cookie banners, footers)
  → chunk (split by runbook section, ~350 tokens each; a whole procedure stays together)
  → tag   (vendor, product, version, doc type, section, line numbers)
  → validate (missing metadata or empty docs stop the run)
  → embed (Gemini turns each chunk into a 768-number vector)
  → index (saved in ChromaDB under storage/)
```

**B. Query (every question): `POST /api/query`**

```
question + product + version
  → embed the question (same Gemini model)
  → search ChromaDB for the top 5 chunks WHERE version = the selected one
  → if even the best match scores below 0.65 → "no grounded answer" (LLM is not called)
  → otherwise send those chunks to Gemini with strict rules ("answer only from these, cite S1/S2…")
  → Gemini returns JSON (summary, steps, commands, sources)
  → we drop any step that cites a source we didn't give it
  → UI shows the steps + source panel
```

Key terms:
- **Chunk**: one small piece of a document, usually one runbook procedure or section.
- **Embedding**: a list of numbers that captures meaning. Similar text gives similar numbers.
- **Vector database (ChromaDB)**: stores embeddings and finds the closest ones quickly (HNSW index).
- **Grounded**: the answer comes only from our documents, never from the LLM's general knowledge.
- **Relevance threshold (0.65)**: minimum similarity score. Below it, we answer "not found".

---

## 4. Who owns what

| Member | Owns | Main files |
| --- | --- | --- |
| **Naman Binu** | Ingestion: loaders, cleaning, chunking, validation, adding docs | `app/ingest/`, `data/corpus/`, `scripts/ingest.py` |
| **Shubham Padkonde** | Embeddings, vector store, retrieval tuning, evaluation | `app/embeddings.py`, `app/vectorstore.py`, `eval/`, `scripts/evaluate.py` |
| **Akash Kolhe** | LLM layer, prompts, RAG pipeline, API, web UI, deployment | `app/llm.py`, `app/prompts/`, `app/rag.py`, `app/main.py`, `web/`, `render.yaml` |
| **Everyone** | PRD, mock UX, README, demo | `docs/`, `README.md` |

Everyone should be able to **explain the whole flow in section 3** during the evaluation, not
just their own part.

---

## 5. Set up on your laptop (~10 minutes)

You need Python 3.11+ and Git.

```bash
git clone https://github.com/Naman1369/telecom-runbook-rag.git
cd telecom-runbook-rag
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**Get your own free Gemini API key** at https://aistudio.google.com/apikey, then:

```bash
cp .env.example .env      # Windows PowerShell: copy .env.example .env
```

Open `.env` and paste your key after `GEMINI_API_KEY=`. **Never commit `.env` and never
share your key in chat or WhatsApp.**

Build the index and start the app:

```bash
python scripts/ingest.py          # builds storage/ (takes a few seconds)
uvicorn app.main:app --reload     # then open http://localhost:8000
```

Useful commands:

```bash
pytest                                  # offline tests, ~3 s, no key needed
python scripts/ingest.py --dry-run      # preview chunks without calling the API
python scripts/ask.py "Cell 3 is down, how do I restart it?" --product HX-5G-gNB --version 23.1
python scripts/evaluate.py              # full evaluation (uses the API, ~3 min because of rate limits)
```

---

## 6. Where to find things

```
app/
  config.py        all settings, read from .env
  ingest/          loaders.py · cleaning.py · chunking.py · pipeline.py
  embeddings.py    Gemini embeddings (batching, retries, cache) + offline test embedder
  vectorstore.py   ChromaDB collection, version filter, product/version catalog
  llm.py           Gemini client, JSON output, model fallback
  prompts/         system.md and answer.md (edit prompts here, not in Python)
  rag.py           the query pipeline (retrieve → prompt → cite → fallback)
  main.py          FastAPI endpoints + serves the web UI
web/               index.html · styles.css · app.js
data/corpus/       the documents (synthetic sample: 2 fictional vendors × 2 releases)
eval/              golden_set.jsonl (21 test questions) · embedding_probes.json
tests/             pytest suite
docs/              PRD · DESIGN · EVALUATION · MOCK_UX · TEAM_WORKFLOW · this file
```

| Want to… | Look at |
| --- | --- |
| Understand the requirements | [PRD.md](PRD.md) |
| Know why we chose section-aware chunking, threshold 0.65, the models | [DESIGN.md](DESIGN.md) |
| See which Sprint roadmap item (3.1–3.32) is where | [DESIGN.md](DESIGN.md), "Roadmap coverage" table |
| See the UI plan | [MOCK_UX.md](MOCK_UX.md) |
| Follow the Git process | [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) |
| Add new documents | [data/corpus/README.md](../data/corpus/README.md) |

---

## 7. Making a change (Git workflow)

```bash
git checkout main && git pull
git checkout -b feat/<short-name>        # e.g. feat/fibre-cut-runbook
# ...make changes...
pytest
git add <files> && git commit -m "feat: add fibre cut runbook"
git push -u origin feat/<short-name>
```

Then open a Pull Request on GitHub, fill in the template, and ask a teammate to review. Details
are in [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md).

---

## 8. Remaining work before the deadline

| # | Task | Owner | Notes |
| --- | --- | --- | --- |
| 1 | Accept the GitHub collaborator invite, clone, run locally | Shubham, Akash | Section 5 |
| 2 | ~~Deploy to Render~~ ✅ done | Naman | Every push to `main` redeploys automatically; the key lives only in the Render dashboard |
| 3 | Add 1–2 more runbooks (e.g. fibre cut, power outage) + golden questions | Naman | Re-run `ingest.py` and `evaluate.py` |
| 4 | Re-run the evaluation after any change and update EVALUATION.md | Shubham | |
| 5 | Rehearse the demo (section 9) and split who presents what | Everyone | |

---

## 9. Demo script (about 5 minutes)

1. **Problem** (30 s): engineers lose time in outages searching docs, and commands differ per release.
2. **Version-awareness** (the key moment):
   - AX-9000 **8.1** → *"BGP peer 10.0.0.2 is stuck in Idle. How do I reset it without dropping routes?"*
     → `reset bgp neighbor 10.0.0.2 soft`
   - Switch to **7.4** and ask the same question → `clear ip bgp 10.0.0.2 soft`
   - Click a citation number to show the exact runbook section and line numbers.
3. **Trap question**: HX-5G-gNB **22.3** → *"How do I run the built-in VSWR test?"* This test only
   exists in 23.1, and the app does **not** give the 23.1 command.
4. **Not found**: AX-9000 8.1 → *"How do I configure segment routing TI-LFA?"* → "no grounded
   answer", with no hallucination.
5. **Follow-up**: after a cell-down answer, ask *"what if that doesn't work?"*. It keeps the
   incident context.
6. **Metrics** (30 s): show the evaluation table from section 2.

All example questions are also in the **"Try"** list in the app's left panel.

Demo from the live app: https://noc-copilot.onrender.com. The free plan sleeps after 15 minutes without traffic, and the first
request then takes about a minute. **Open it 2–3 minutes before presenting.**

---

## 10. Troubleshooting

| Problem | Fix |
| --- | --- |
| Badge says **"GEMINI_API_KEY missing"** | Add the key to `.env`, then **restart** uvicorn (`.env` is read at startup). |
| Badge says **"Index not built"** | Run `python scripts/ingest.py`. |
| `503 high demand` / slow answers | Gemini is overloaded; the app automatically falls back to `CHAT_FALLBACK_MODELS`. Wait and retry. |
| `429` during `evaluate.py` | Free-tier rate limit; run `python scripts/evaluate.py --sleep 10`. |
| `404 model not found` | Your key can't use that model. List available models (command in `.env.example`) and change `CHAT_MODEL`. |
| Changed docs but answers didn't change | Re-run `python scripts/ingest.py` and restart the server. |
| `ModuleNotFoundError` | Activate the venv first (`.venv\Scripts\activate`). |

---

*The sample documents are synthetic. "Aurora Networks" and "Helix Radio" are fictional vendors
made up for this project, so say this if the evaluators ask.*
