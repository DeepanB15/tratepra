import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import dashboard, dossiers, monitoring, history, internal, research, saved, sources, trends
from app.core import health
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import setup_logging

settings = get_settings()
log = logging.getLogger(__name__)
MAX_BODY_BYTES = 64 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    if settings.is_production:
        problems = settings.security_problems()
        if problems:
            raise RuntimeError("Insecure configuration: " + "; ".join(problems))
    elif settings.security_problems():
        log.warning("Development mode: %s", "; ".join(settings.security_problems()))
    if settings.auto_create_tables:
        init_db()
    from app.services.source_service import ensure_sources

    try:
        ensure_sources()
    except Exception as exc:  # DB not migrated / unreachable: /ready reports it, the app still starts
        log.error("Could not register sources (is the schema migrated?): %s", exc)
    from app.monitoring.jobs import start_scheduler, stop_scheduler

    start_scheduler()  # no-op unless MONITORING_SCHEDULER_ENABLED=true
    yield
    stop_scheduler()
    from app.services.dossier_service import shutdown_workers

    shutdown_workers()


app = FastAPI(title="Tratepra API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Limit", "X-Offset"],
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"error": "payload_too_large", "detail": "Request body too large"})
    return await call_next(request)


# ---- structured errors; internal details and stack traces are logged, never returned ----
@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": "http_error", "detail": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    parts = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "validation_error", "detail": "; ".join(parts)})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    request_id = uuid.uuid4().hex[:12]
    log.exception("Unhandled error [%s] on %s %s", request_id, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Internal server error", "request_id": request_id},
    )


@app.get("/health")
def liveness():
    """Process is up. Does not touch dependencies."""
    return {"status": "ok", "service": "tratepra", "version": "1.0.0"}


@app.get("/ready")
def ready():
    """Dependency readiness: database, pgvector, Ollama, connector availability."""
    report = health.readiness()
    return JSONResponse(status_code=503 if report["status"] == "not_ready" else 200, content=report)


app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
app.include_router(dossiers.router, prefix="/api/research/dossiers", tags=["dossiers"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(trends.router, prefix="/api/trends", tags=["trends"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(saved.router, prefix="/api/saved", tags=["saved"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(internal.router, prefix="/api/internal", tags=["internal"])
