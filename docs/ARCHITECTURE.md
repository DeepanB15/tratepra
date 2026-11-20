# Architecture

Modular monolith: FastAPI + PostgreSQL/pgvector + React/TypeScript/Tailwind. See `diagrams/system_architecture.mmd`.

## Research flow (`POST /api/research/search`)
1. `query_processor` – clean query, keywords, intent, time-range phrases.
2. Shared ingestion pipeline (`ingestion/`): `collector` runs the selected connectors **in parallel** (thread pool; DB writes afterwards on one thread), `resilience` retries transient failures with exponential backoff (honours short `Retry-After`, never retries auth/quota errors), `filters` applies the date window (undated records are reported, not given invented dates), `normalizer` maps to the unified schema, `deduplicator` removes duplicates (source id, canonical URL, content hash, then token-Jaccard near-duplicates within a source). Failures are recorded per source, never hidden.
3. `embedding_store.embed_pending` – Sentence Transformer vectors into pgvector.
4. `retriever` – cosine search filtered by source and time window.
5. `ranker` – `R = 0.45S + 0.25K + 0.20F + 0.10Q` (weights in config, initial heuristics). K = 80% token overlap (light stemming + small synonym table) + 20% adjacent-phrase match. Engagement is kept for the Trend Engine, not used to boost research ranking.
6. `context_builder` – top evidence with a per-source cap, numbered `[n]`.
7. `synthesizer` – Ollama (Qwen) JSON answer; clearly labelled extractive fallback if the LLM is down.
8. `citation_validator` – `[n]` references not backed by evidence are removed.
9. Persist query, result, evidence; return structured JSON.

## Trend flow (`scripts.run_trend_analysis` / `POST /api/internal/trends/recompute`)
Eligible dated text documents -> preprocessing -> stored embeddings -> BERTopic (UMAP -> HDBSCAN -> c-TF-IDF, seeded) -> per-topic weekly volumes (6 windows) -> growth, momentum, novelty, engagement, search interest, cross-source -> Trend Score + lifecycle -> new `trend_observations` row per topic.

Topics are matched to the previous run by centroid similarity (>= 0.80) so a topic keeps its id and its observation history. Old observations are never overwritten.

Design rules: Google Trends rows are search-interest observations; they are stored but excluded from retrieval and topic modeling. Connectors never invent timestamps or engagement; missing values are `None`.
