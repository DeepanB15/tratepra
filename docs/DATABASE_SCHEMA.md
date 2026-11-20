# Database schema

PostgreSQL + pgvector, hosted on Supabase (see [SUPABASE.md](SUPABASE.md)) or run locally. Tables are created on startup (`init_db`); Alembic is configured in `backend/migrations` (generate the first revision with `alembic revision --autogenerate -m init`).

| Table | Purpose |
| --- | --- |
| `sources` | Registered connectors, quality prior, last status/error |
| `documents` | Normalized articles/videos/posts/search-interest points. Unique `(source_id, external_id)`; `canonical_url`, `content_hash` for dedup; `published_at` and `collected_at` kept separate; raw `engagement` and `metadata` JSON |
| `document_embeddings` | `vector(EMBEDDING_DIM)` per document + model name |
| `topics` | Name, terms, centroid embedding, model version, run id |
| `topic_documents` | Document-to-topic assignment (+probability); noise is not stored as a topic |
| `trend_observations` | Append-only history: window, volume, each signal, score, lifecycle, coverage, raw signals, formula/model version |
| `research_queries` / `research_results` / `research_evidence` | Query, answer + metadata (model, latency, retrieval metadata), cited evidence with rank/relevance |
| `saved_items` | Saved research/trends (unique per item) |
| `collection_logs` | One row per connector run: status, counts, error, duration |

`EMBEDDING_DIM` must match the embedding model (384 for `all-MiniLM-L6-v2`). Changing models requires re-embedding and a new vector column size. See `diagrams/database_er.mmd`.
