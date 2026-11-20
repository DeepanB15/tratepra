# Implemented vs planned

Status is claimed only with evidence. "Verified" names what was actually run.

## Evidence table (by PRD v2.0 workstream)

| Requirement | Status | Evidence |
| --- | --- | --- |
| Alembic initial migration, reversible, no drift | Verified (local PostgreSQL 16 + pgvector 0.6.0) | `test_migration_downgrade_and_reupgrade`; autogenerate reported no drift |
| HNSW / GIN / composite indexes, vector(384), unique constraints | Verified (local) | `test_schema_has_pgvector_indexes_and_dimension`, `test_unique_source_external_id` |
| `/health`, `/ready` (DB, pgvector, Ollama) | Verified (local DB; Ollama reported down honestly) | `test_ready_reports_database_and_pgvector_on_real_postgres`, `verify_setup` output |
| Production security checks, constant-time token, body limit, structured errors | Verified by unit/API tests | `test_security_config.py`, API tests |
| Connector state from facts; Google Trends endpoint config + strict parser | Verified by unit tests | `derive_state` tests, connector tests |
| Collection logs per run; validation; dedupe | Verified by pipeline tests (fake connectors, labelled as such) | `test_ingestion_pipeline.py` |
| Hybrid retrieval (pgvector + full-text) | Verified on real PostgreSQL with hash embeddings | `test_hybrid_retrieval_*` |
| Diverse evidence, claim-level citation verification, transparency, honest fallback | Verified by unit + pipeline tests | `test_research_v2.py`, `test_research_pipeline.py` |
| Language guard, one-to-one topic matching, lifecycle guard, score explanation | Verified by unit tests; explanation/detail API verified on real DB | `test_trends_v2.py`, `test_trends_dashboard.py` |
| Dashboard counts, lifecycle distribution, source freshness; Sources page; research transparency; trend explanation | Verified: `tsc`, `vite build`, screenshots against local backend, vitest | frontend build + 6 tests |
| `package-lock.json` committed | Done | `frontend/package-lock.json` |
| Evaluation package + datasets | Done; lifecycle cases synthetic; retrieval set unlabelled | `scripts.evaluate`, `docs/EVALUATION.md` |

## Not verified (external dependencies)
- **Supabase**: the migration and SSL/pooler connection were not run against a real project.
- **Ollama / Qwen**: synthesis with the real model not run; fallback path is tested.
- **Sentence Transformers and BERTopic on real data**: not run; trend recompute end to end is untested.
- **Live connectors**: Google News, YouTube (needs key), Reddit (needs approval) not called. Google Trends has no public endpoint documented; it stays unavailable until `GOOGLE_TRENDS_API_ENDPOINT` + key are set.
- **Retrieval and answer quality**: unmeasured; needs human-labelled queries.

## Planned / known gaps
- Authentication, scheduled collection
- Weight tuning and topic-quality evaluation on real data
- Browser-level end-to-end UI tests
