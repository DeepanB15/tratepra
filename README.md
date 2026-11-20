# Tratepra

AI-powered Research & Trend Intelligence Platform (V1.0).

Tratepra researches a topic across Google News, YouTube, Google Trends and Reddit, writes a cited answer with a local LLM (Ollama + Qwen), discovers topics with BERTopic, and scores emerging trends with an explainable, historical Trend Score.

> V1 is a working, reproducible MVP with a production-oriented architecture. It is **not** claimed production-ready. See [docs/IMPLEMENTED_VS_PLANNED.md](docs/IMPLEMENTED_VS_PLANNED.md).

## Modules

| Module | Location |
| --- | --- |
| AI Research Engine | `backend/app/research/`, `services/research_service.py` |
| Trend Intelligence Engine | `backend/app/intelligence/`, `services/trend_service.py` |
| Research Dashboard | `frontend/` |
| Source connectors (shared) | `backend/app/connectors/` |

## Quick start

Prerequisites: Docker, a Supabase project (or local Postgres + pgvector), and [Ollama](https://ollama.com) running on the host.
Prerequisites: Docker, a Supabase project (or local Postgres + pgvector), and [Ollama](https://ollama.com) running on the host.

```bash
cp .env.example .env            # set DATABASE_URL (Supabase) and any connector keys
ollama pull qwen3.5:4b          # the model named in OLLAMA_MODEL
docker compose up --build       # backend (:8000) + frontend (:5173)
```

Database options (details in [docs/SUPABASE.md](docs/SUPABASE.md)):
- **Supabase (recommended):** enable the `vector` extension, paste the connection string into `DATABASE_URL`.
- **Local Postgres:** `docker compose -f docker-compose.yml -f docker-compose.local-db.yml up --build`.

Without Docker:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                   # create/upgrade the schema (needs pgvector)
python -m scripts.verify_setup         # real check: DB, pgvector, Ollama, connector config
uvicorn app.main:app --reload

cd ../frontend
npm install && npm run dev
```

If the backend runs inside Docker and Ollama on the host, the compose file already points `OLLAMA_BASE_URL` at `host.docker.internal`.

## Populate data and compute trends

Trends need a few weeks of dated documents spread over several topics. Collect for several queries, then run the trend pipeline; repeat periodically (each run appends a new observation).

```bash
cd backend
python -m scripts.collect_data "AI coding agents" "LLM agents" "open source LLM" --range 30d
python -m scripts.process_documents          # embeddings (also runs automatically)
python -m scripts.run_trend_analysis         # BERTopic + temporal analysis + scoring
```

The same operations exist as protected endpoints (`X-Internal-Token` header = `INTERNAL_API_TOKEN`): `POST /api/internal/collection/run`, `GET /api/internal/collection/status`, `POST /api/internal/trends/recompute`.

## Health and verification

- `GET /health` - liveness only. `GET /ready` - database, pgvector (incl. embedding dimension) and Ollama; `503` if the database or pgvector fail, `degraded` if only Ollama is down.
- `python -m scripts.verify_setup [--probe]` prints what each real service answered. `--probe` makes one live request per configured connector.
- Set `APP_ENV=production` to enforce a strong `INTERNAL_API_TOKEN` and non-wildcard `CORS_ORIGINS` at startup.

## Tests

```bash
cd backend && pytest                                   # unit tests (integration tests skip without a database)
TEST_DATABASE_URL=postgresql+psycopg2://user@host:5432/scratch_db pytest   # + real PostgreSQL/pgvector tests (DROPS that DB's schema)
cd frontend && npm test && npm run build
python -m scripts.evaluate                             # evaluation report (see docs/EVALUATION.md)
```

See [docs/TESTING.md](docs/TESTING.md) for what each layer does and does not prove.

## Connectors and access

| Connector | Needs | Without it |
| --- | --- | --- |
| Google News | nothing | – |
| YouTube | `YOUTUBE_API_KEY` | marked unavailable |
| Google Trends | official alpha access (`GOOGLE_TRENDS_API_KEY`) or the experimental `pytrends` fallback (`GOOGLE_TRENDS_ALLOW_FALLBACK=true`) | marked unavailable; search-interest signal is excluded from scoring |
| Reddit | registered app + approval (`REDDIT_CLIENT_ID/SECRET`) | marked unavailable |

Unavailable sources are reported in the UI and API; no data is ever simulated. Verify Reddit commercial-use approval and your Google Trends API access before relying on either. Reddit's policies and API access have been changing; check the current terms.

## Docs

`docs/` has product scope, architecture, database schema, API, data sources, trend scoring, implemented-vs-planned (with evidence), implementation plan, testing, evaluation, Supabase/migrations, a release checklist and a demo guide. Diagrams are Mermaid files in `diagrams/`.
