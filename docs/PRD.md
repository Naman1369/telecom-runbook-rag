# PRD — NOC Copilot: Version-Aware Telecom Documentation RAG

| | |
| --- | --- |
| Delivery cycle | Kalvium Sprint 2 (deadline 30 Sep 2026) |
| Team | 3 members, see [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) |
| Status | V1 build |

## 1. Problem

A telecom operator maintains **network configuration guides, troubleshooting runbooks and
vendor manuals** for many equipment types, each across several software releases. During an
outage, a support engineer has to find the one resolution step that applies to the failing
element's release. Today that means searching several PDFs and wiki pages by hand while the
outage clock runs.

### Why it happens
- **Fragmented documentation.** Runbooks, config guides, vendor manuals and release notes are in
  different formats and places, with no unified index.
- **No release awareness.** Search returns results from every software release. Commands and
  alarm names change between releases (e.g. `clear ip bgp` in AuroraOS 7.4 became
  `reset bgp neighbor` in 8.1), so the wrong-release answer can make the outage worse.
- **No traceability.** Answers from colleagues or generic chatbots do not point to the exact
  runbook section, so engineers cannot verify them under pressure.

### Impact
| Area | Effect |
| --- | --- |
| MTTR | Minutes lost searching docs extend every outage and risk SLA penalties. |
| Change safety | Commands from the wrong release fail or cause further damage. |
| Escalations | L1 engineers escalate to L2/vendor TAC for questions the docs already answer. |
| Trust | Engineers stop trusting documentation and rely on tribal knowledge. |

## 2. Users

- **Primary: NOC / field support engineer (L1–L2)** during an incident. Needs the exact steps
  and commands, fast, with a source they can trust.
- **Secondary: documentation owner.** Publishes new release docs and needs them searchable
  without manual tagging work.

## 3. Goal & success metrics

Answer engineer questions with responses that are (1) scoped to the correct equipment release
and (2) grounded in an exact, citable source passage.

| Metric | Target |
| --- | --- |
| Answers with a correct source citation | ≥ 90% |
| Answers scoped to the correct release | ≥ 95% |
| Median response time | < 3 s |
| Doc-related support tickets / escalations | −50% (post-launch) |

## 4. Scope (V1)

**In scope:** multi-format ingestion (Markdown, HTML, TXT, PDF), cleaning, section-aware
chunking, metadata tagging, embeddings, version-filtered retrieval, grounded JSON generation
with citations, "not found" fallback, a minimal web app, follow-up questions within an
incident, evaluation harness.

**Out of scope:** automatic re-ingestion on every doc commit, fine-tuning, multi-language docs,
authentication/SSO, write access to network elements.

## 5. User stories

1. As an engineer, I pick *AX-9000 / 8.1*, type "BGP peer stuck in Idle", and see numbered
   steps with copyable commands, each linked to the runbook section.
2. As an engineer, I ask a follow-up ("what if the soft reset doesn't work?") without repeating
   the context.
3. As an engineer, when the docs don't cover my question, I am told clearly so I escalate
   instead of trusting a guess.
4. As an engineer, if I mention the release in my question ("on 23.1…"), the app detects it.
5. As a doc owner, I drop new files into `data/corpus/<vendor>/<product>/<version>/` and run
   one command to re-index. Invalid metadata is reported before indexing.

## 6. Functional requirements

| # | Requirement |
| --- | --- |
| F1 | Ingest md/html/txt/pdf, preserving file, vendor, product, version and URL. |
| F2 | Strip boilerplate (navigation, cookie banners, footers) and normalise whitespace/encoding. |
| F3 | Chunk by document section with token limits and overlap; each chunk records its section path and line range. |
| F4 | Validate metadata before indexing; the run fails on missing fields or empty documents. |
| F5 | Embed in batches with retry/backoff and a content-hash cache (no duplicate API work). |
| F6 | Embedding quality probes: related text must score above unrelated text. |
| F7 | Top-k retrieval hard-filtered on product + version (optional doc-type filter). |
| F8 | LLM answers only from retrieved excerpts, as schema-validated JSON. |
| F9 | Every step carries citations. Steps citing unknown excerpts are dropped. |
| F10 | Below the relevance threshold, or when the model finds no answer, return "not found". |
| F11 | Log every interaction (question, release, citations, latency, tokens, cost). |

## 7. Non-functional requirements

- Median latency < 3 s (Flash-Lite model with fallback, top-k 5, ~6k-token context cap).
- API keys only in `.env`, never committed.
- Cost visibility: token and USD estimates per query and per ingestion run.

## 8. Risks & mitigations

| Risk | Level | Mitigation |
| --- | --- | --- |
| Ungrounded / hallucinated steps | High | Strict system prompt, JSON schema, citation validation, not-found fallback |
| Inconsistent legacy metadata | Medium | Folder-path convention + validation step before indexing |
| Stale index | Medium | One-command re-ingest; cache makes it cheap; scheduled job in V2 |
| Free-tier rate limits | Medium | Retry/backoff, embedding cache, paced evaluation |

## 9. Milestones (Sprint 2)

| Milestone | Roadmap items |
| --- | --- |
| Kick-off, PRD, mock UX | 3.1, 3.8, 3.9 |
| Environment + repo workflow | 3.2, 3.10, 3.11 |
| LLM API basics (client, prompts, tokens, params, JSON, templates) | 3.12 – 3.18 |
| Document processing & chunking | 3.3, 3.19 – 3.24 |
| Embeddings | 3.4, 3.25 – 3.29 |
| Vector store & retrieval | 3.5, 3.30 – 3.32 |
| RAG pipeline & app delivery | 3.6, 3.7 |
