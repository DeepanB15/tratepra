# Phase 1 Test Report

Environment: sandbox with PostgreSQL 16 + pgvector 0.8 (local, port 5544), Python 3.13, BERTopic 0.16.4 / UMAP / HDBSCAN, Node 22. Embedding model, Ollama and connectors are deterministic fakes in tests, so tests prove **pipeline / database / API behaviour — not real-embedding quality**.

## Results
| Suite | Result |
|---|---|
| Backend (unit + PostgreSQL integration) | **162 passed, 0 failed** (baseline was 93 passed / 4 failed) |
| ↳ new Phase 1 tests | 65 (27 unit, 17 run/idempotency/migration integration, 21 API integration) |
| Frontend vitest | **11 passed** (5 pre-existing + 6 new) |
| Frontend `tsc --noEmit` + `vite build` | pass |
| Browser end-to-end (Playwright, real backend + Vite dev server, synthetic seeded DB) | pass, no console errors |

## What the new tests prove
- **Run key**: deterministic, order-independent, changes with documents / window / configuration; UTC-day anchoring incl. IST and naive inputs.
- **Idempotency**: identical rerun → `unchanged`, run/observation/topic counts identical; changed data → new run, same topic ids (continuity), history keeps both observations; next-day rerun → new run.
- **Failed runs**: exception rolls back all writes, previous observations/topic state unchanged, error scrubbed of credentials, overview still shows last successful run, no topic becomes stale; retry reuses the failed row (`attempts=2`); crashed `running` rows time out and are retried; concurrent `running` blocks duplicate execution.
- **Insufficient / empty / all-noise** inputs recorded as failed runs with reason; no topics created. Noise stays identifiable (counts and per-source noise).
- **Validation**: every rejection reason; `input = kept + rejected`; embedding-model mismatch recorded in the run.
- **Identity**: new, matched (one-to-one), potential split (never inherits parent id), potential merge, uncertain.
- **Freshness**: stale at 1 missed completed run, inactive at 4; hidden from default list; filterable; age measured against the latest completed run.
- **Naming / diagnostics / explanations**: generic-name flagging, measured coverage, size distribution, high-noise and overly-broad flags, spike-vs-sustained classification, evidence-only summaries.
- **BERTopic (real library, synthetic vectors)**: two fits give identical assignments (reproducible); `n_noise` equals the number of `-1` assignments; `min_df` fallback exercised and recorded.
- **Database**: unique run key, status CHECK, unique `(topic_id, run_id)`, legacy NULL-run rows unconstrained, migration 003 upgrade/downgrade, backfill + legacy-row preservation, **idempotent upgrade after `create_all`**.
- **API**: 11 invalid-parameter cases → 422; pagination + headers; every filter; asc/desc sorting with nulls last; detail/history/overview/runs contracts; 404s; no secrets in run output; tz-aware timestamps.

## Browser workflow (synthetic data, real HTTP)
1 open Discovery → 2 real trends rendered → 3 filter emerging (URL state) → 4 open trend → 5 score, coverage, explanation, contribution table → 6 history charts → 7 representative source link target verified (`href`, not clicked externally) → 8 back to Discovery. Also: Runs details, Sources data-health strip, mobile viewport (390 px, no horizontal scroll), backend-unreachable error state with Retry.

## Not tested here (honest gaps)
- Docker Compose build/start, container health/readiness, frontend→backend in containers (no Docker daemon in the sandbox).
- Real Supabase database, real Sentence-Transformer embeddings, real BERTopic output on your data.
- Windows-specific workflow.
- Accessibility audit beyond semantic markup/labels/aria; no automated a11y tooling run.
