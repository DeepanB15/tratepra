# Release checklist

Tick an item only with evidence (output pasted into the release notes). Items marked **ext** depend on something outside this repository.

## Automated
- [ ] `cd backend && TEST_DATABASE_URL=... pytest` all pass, with the integration tests **not** skipped
- [ ] `cd frontend && npm test && npm run build`
- [ ] `python -m scripts.evaluate` runs; lifecycle accuracy 100%

## Database
- [ ] **ext** `alembic upgrade head` on the real Supabase project; `GET /ready` shows database and pgvector OK
- [ ] `AUTO_CREATE_TABLES=false` in production

## Services
- [ ] **ext** `python -m scripts.verify_setup --probe` with real keys: each connector line is OK or an explained unavailable
- [ ] **ext** Ollama reachable with the configured `OLLAMA_MODEL`; a research query returns a non-fallback answer
- [ ] **ext** Google Trends: confirm official API access and set `GOOGLE_TRENDS_API_ENDPOINT`; otherwise the source stays unavailable and the search-interest signal is excluded
- [ ] **ext** Reddit: app approval granted for the intended use

## Data and quality
- [ ] Collection run twice: second run inserts ~0 duplicates; `/api/sources/logs` shows both runs
- [ ] Trend analysis run on real data twice: two observations per matched topic; inspect topic names/terms by eye
- [ ] Label at least 10 queries in `research_queries.json` and record precision@5 / MRR
- [ ] Source failure (e.g. missing key) visible on the Sources page

## Security
- [ ] `APP_ENV=production`, strong `INTERNAL_API_TOKEN`, explicit `CORS_ORIGINS`; backend refuses to start otherwise
- [ ] No secrets in the frontend env
