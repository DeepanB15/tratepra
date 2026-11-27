# Phase 2 Audit — Evidence Intelligence & Research Dossier Engine

Scope: source inspected at branch `phase-1-discovery-engine` (commit `3fc12c3`). Everything below is read from the code, not assumed. Items not verified are marked **unverified**.

## 1. Existing research capabilities
- Ad hoc question answering: `POST /api/research/search`, `GET /api/research/history`, `GET /api/research/{id}`.
- Pipeline (`services/research_service.run_research`): optional live collection → embedding of pending docs → `query_processor` → hybrid `retriever` → `ranker` → `context_builder.select_evidence` → Ollama `synthesizer` (extractive fallback) → `citation_validator.verify_answer` → persistence.
- Persisted: `ResearchQuery`, `ResearchResult` (answer, key findings, source status/distribution, `retrieval_metadata` JSON), `ResearchEvidence` (rank, relevance, cited).
- No dossier, claim-level, contradiction, gap or evidence-quality concept exists.

## 2. Retrieval workflow
- Semantic: pgvector cosine over `DocumentEmbedding` (384-dim, HNSW). Keyword: `ts_rank_cd` over a GIN index on `to_tsvector('english', normalized_text)`; OR-tsquery, phrases as `<->`.
- Ranker `R = 0.45·S + 0.25·K + 0.20·F + 0.10·Q` (config `rank_*`), K computed on full `normalized_text`, small synonym table.
- Evidence selection: max 10 items, 5 per source, title-Jaccard repetition skip.
- Query processing yields keywords, phrases, intent (trend/comparison/explanation/general), time range. **Missing:** entity typing, topic-id handling, per-stage diagnostics (rejection reasons), phrase/entity match bonuses, date-coverage reporting.

## 3. Article enrichment coverage
- Google News only, 5 documents per run (`article_enrichment.py`); SSRF-safe bounded fetch (`article_fetcher.py`); trafilatura extraction, 20,000-char cap, 300-char minimum.
- Fetcher returns `None` on every failure, so **the failure reason is lost**.
- Status is stored only on success in `metadata["article_extraction"]`. There are no durable states for failed / too short / unavailable / RSS-only, no extraction timestamp column, no article hash.
- `normalizer.content_hash` hashes RSS title+description only.

## 4. Citation verification approach
- Deterministic: reference-existence check plus lexical content-token overlap (≥ 0.2) against each cited item. This is a **heuristic, not entailment**; it can pass a claim that shares words with a source but says something different, and can fail a correct paraphrase. This limitation must be kept visible in product text.
- Evidence text used for verification = title + RSS description only.

## 5. Database entities (relevant)
`Document` (normalized_text, metadata JSON, published_at, collected_at), `DocumentEmbedding` (embedding, model, text_hash), `Topic`, `TopicDocument`, `TrendObservation`, `TrendRun`, `ResearchQuery/Result/Evidence`, `SavedItem`. Migrations 001–003; `AUTO_CREATE_TABLES=true` means migrations must stay idempotent.

## 6. APIs
Research: `/search`, `/history`, `/{id}`. Trends (Phase 1): list, detail (topic terms, representative documents, related topics), history, runs. No dossier endpoints.

## 7. Frontend
`Research.tsx` (search box → `ResearchView`; sources and range only; no history on page, no insufficient-evidence state beyond empty text, no dossier creation). `TrendDetail.tsx` has no investigate action. Shared `components/common/ui.tsx`, services `api.ts` (`apiPage` returns `{data,total}`).

## 8. Confirmed defect — article text is not used where it matters
Verified in code:
| Stage | Text used | Includes article text? |
|---|---|---|
| FTS index / keyword rank | `normalized_text` | Yes (collector concatenates `_article_text`) |
| Embedding + `text_hash` | `normalized_text` | Yes in the hash; embedding models truncate long input (**unverified** how much article text reaches the vector) |
| LLM context (`context_builder`) | `description[:500]` | **No — RSS description only** |
| Citation validation | title + description | **No** |

Consequence: a document can be *retrieved* because of article text the LLM never sees, and claims grounded in article text would be flagged unverified. There is also no way to tell a full article from an RSS-only item. **Fix in this phase:** persist article text and extraction state separately, build bounded query-relevant excerpts from article text when status is full/partial, and verify against the same excerpt text that was shown to the model. RSS-only documents keep current behaviour and are labelled RSS-only.

## 9. Missing capabilities and proposed changes
1. Article evidence state model (additive columns/table), reasons surfaced from the fetcher, stale-embedding detection tied to the real normalized text.
2. Query processor: entities, topic-id support; retrieval diagnostics, phrase/entity/time signals, source-diversity and duplicate handling.
3. Dossier engine (sections A–G), deterministic claim extraction and verification, contradiction and gap detection, transparent evidence-quality dimensions.
4. Additive migration `004`: `research_dossiers`, `dossier_claims`, `claim_evidence`, `dossier_evidence`; reuse `Document`, no content duplication.
5. Dossier API + schemas, bounded background execution with persisted status, duplicate-generation protection, regeneration that preserves the previous result on failure.
6. Frontend: Investigate button, Dossier page, Evidence Explorer, Claim view, improved Research page.
7. Evaluation tooling and a measured quality report; no fabricated numbers.

## 10. Risks
- Sandbox has no real corpus, Ollama or embedding model: real-data evaluation and LLM quality cannot be measured here; scripts and a protocol will be provided and results reported as not run.
- Contradiction detection without an NLI model is lexical/polarity-based and will be conservative; it will be labelled as such.
- Embedding model truncation may mean article text barely affects vectors; FTS carries it instead (to be measured when a corpus is available).
- User's uncommitted changes to `embedding_store.py` and its test must not be overwritten or committed by this work.
- Prompt tail truncated at Stage 11 (e2e step 7); Phase 1 acceptance conventions applied beyond that point.
