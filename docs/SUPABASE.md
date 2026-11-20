# Supabase as the managed database

Tratepra uses Supabase only as managed PostgreSQL + pgvector. FastAPI keeps all business logic (ingestion, research, trend analysis, Ollama calls).

## Setup
1. Create a Supabase project.
2. SQL Editor -> run `CREATE EXTENSION IF NOT EXISTS vector;` and confirm it is enabled (Database -> Extensions). The app also tries this on startup and logs a warning if the role is not allowed to.
3. Dashboard -> Connect -> copy the connection string (session pooler works from most networks) into `.env` as `DATABASE_URL`. URL-encode special characters in the password.
4. Apply the schema: `cd backend && alembic upgrade head` (migration `001_initial_schema` also runs `CREATE EXTENSION IF NOT EXISTS vector`). Production should keep `AUTO_CREATE_TABLES=false` so Alembic is the only schema writer; `true` is a development convenience.
5. Run `python -m scripts.verify_setup` and `GET /ready` to confirm connectivity and the 384-dimension vector column.

## What the app does with the URL
`app/core/database.py:normalize_database_url` accepts `postgres://`, `postgresql://` and `postgresql+asyncpg://` and converts them to `postgresql+psycopg2://`, adding `sslmode=require` for Supabase/pooler hosts unless you set `sslmode` yourself. Pool size is `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` (keep these small; the pooler enforces its own connection limits).

## Why synchronous SQLAlchemy + psycopg2 instead of asyncpg
The research and trend pipelines are dominated by blocking work (HTTP to connectors, sentence-transformer inference, BERTopic, Ollama). The collector runs connector calls in a thread pool and writes to the database afterwards on a single thread. An async driver would add complexity without removing those blocking calls. It also avoids asyncpg's prepared-statement issues behind Supabase's transaction pooler. If you later need an async API layer, only `database.py` and the services need to change.

## Security
- The database password and any Supabase service-role key stay on the backend. Never put them in React / Vite env vars.
- This app does not use Supabase's client SDK or its auto-generated REST API. If you add user accounts later and expose tables through the Supabase API, enable Row Level Security first.

## Local alternative
`docker compose -f docker-compose.yml -f docker-compose.local-db.yml up --build` runs PostgreSQL + pgvector locally and points the backend at it.

## Migrations
- Create: `alembic revision --autogenerate -m "describe change"`, then **read the generated file** before committing.
- Apply / roll back one step: `alembic upgrade head` / `alembic downgrade -1`.
- The initial migration was verified (upgrade, downgrade to base, upgrade again, no autogenerate drift) on a local PostgreSQL 16 with pgvector 0.6.0. It has **not** been run against a real Supabase project from this repository's test environment; do that once and record it in `docs/RELEASE_CHECKLIST.md`.
- Indexes: HNSW (`vector_cosine_ops`) on embeddings, GIN on `to_tsvector('english', normalized_text)`, plus composite indexes for time-window queries.
- Changing `EMBEDDING_MODEL` to one with a different dimension requires a new migration and re-embedding.
