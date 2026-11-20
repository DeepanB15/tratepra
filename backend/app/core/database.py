import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


def normalize_database_url(url: str) -> str:
    """Accept the URL styles people copy from Supabase / docs and return a psycopg2 URL.

    - postgres:// and postgresql:// -> postgresql+psycopg2://
    - postgresql+asyncpg:// -> postgresql+psycopg2:// (this app uses synchronous SQLAlchemy)
    - Supabase / pooler hosts get sslmode=require unless the URL sets it.
    Passwords containing special characters must be URL-encoded.
    """
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://"):]
    parsed = make_url(u)
    if not parsed.drivername.startswith("postgresql"):
        return u
    parsed = parsed.set(drivername="postgresql+psycopg2")
    host = parsed.host or ""
    if ("supabase" in host or "pooler" in host) and "sslmode" not in parsed.query:
        parsed = parsed.update_query_dict({"sslmode": "require"})
    return parsed.render_as_string(hide_password=False)


engine = create_engine(
    normalize_database_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create the pgvector extension and all tables (Alembic is also configured)."""
    from sqlalchemy import text

    import app.models  # noqa: F401  (register models)

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:  # e.g. hosted DB where the extension must be enabled in the dashboard
        log.warning("Could not create the pgvector extension automatically (%s). Enable it in your database: CREATE EXTENSION vector;", exc)
    Base.metadata.create_all(engine)
