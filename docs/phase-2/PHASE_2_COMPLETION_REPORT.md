# Phase 2 Completion Report

**Delivered:** audit; article evidence states (migration 004) and the article-text fix; query entities/topic ids; retrieval diagnostics with rejection reasons; dossier engine (sections A–G), deterministic claim verification, contradiction handling, gap detection, transparent evidence quality; persistence; 6 endpoints; frontend (Investigate button, dossier page, Evidence Explorer, claim view, improved Research page); evaluation tooling; tests.

**Verified:** backend 202 tests pass on isolated PostgreSQL 16 + pgvector (unit + integration, incl. migration 004 up/down/idempotent, duplicate-creation, single-runner claim, failed-refresh preservation, failed-first-generation recovery); frontend 14 vitest tests, type-check, production build; Playwright e2e against a live API on an isolated DB.

**Not verified:** real data, real embeddings, real Ollama, Docker Compose, Supabase. Real quality numbers: none (see RESEARCH_QUALITY_REPORT.md). Source ingestion with live article fetching was unit-tested with mocks only.

**Spec notes:** the prompt was truncated at Stage 11 (e2e step 7); the e2e covers steps 1–6 plus evidence filters, claims and refresh. Article text is stored once in `documents.article_text` and also inside `normalized_text` (needed for FTS/embedding); dossiers never copy it.
