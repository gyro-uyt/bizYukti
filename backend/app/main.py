"""BizYukti API. Run: uvicorn app.main:app --reload"""

import logging
import mimetypes
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import (admin, auth, demands, events, inquiries, me, meta, notifications, opportunities, properties, reports,
                  rewards, saved)
from .config import settings
from .db import engine
from .logging_setup import configure_logging

configure_logging()
log = logging.getLogger("bizyukti.api")
mimetypes.add_type("image/webp", ".webp")  # slim images lack it, so listing photos were served as octet-stream
API = "/api/v1"


def _otel(app: FastAPI) -> None:
    """OpenTelemetry tracing when OTEL_EXPORTER_OTLP_ENDPOINT is set and the optional packages are installed."""
    import os

    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning("OTEL endpoint set but opentelemetry packages are missing (pip install -r requirements-otel.txt)")
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "bizyukti-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    log.info("OpenTelemetry tracing enabled")


def _friendly(err: dict) -> str:
    field = ".".join(str(p) for p in err.get("loc", [])[1:]) or "request"
    return f"Check {field}: {err.get('msg', 'invalid value').removeprefix('Value error, ')}"


def create_app() -> FastAPI:
    app = FastAPI(title="BizYukti API", version="1.0.0", docs_url=f"{API}/docs", openapi_url=f"{API}/openapi.json",
                  redoc_url=None)

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Device-Id", "X-Request-Id"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"request_id": rid, "path": request.url.path})
            response = JSONResponse({"detail": "Something went wrong on our side. Please try again.",
                                     "request_id": rid}, status_code=500)
        ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-Id"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(API) and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        if request.url.path != "/health":
            log.info("%s %s %s %sms", request.method, request.url.path, response.status_code, ms,
                     extra={"request_id": rid, "path": request.url.path, "status": response.status_code,
                            "duration_ms": ms, "method": request.method})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        return JSONResponse({"detail": _friendly(errors[0]) if errors else "Invalid request.",
                             "errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in errors]}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):  # structured errors: {"code", "message", ...}
            return JSONResponse({"detail": detail.get("message", ""), **detail}, status_code=exc.status_code,
                                headers=getattr(exc, "headers", None))
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    for module in (auth, me, meta, demands, properties, opportunities, reports, saved, inquiries, rewards, notifications,
                   admin, events):
        app.include_router(module.router, prefix=API)

    @app.get("/health", include_in_schema=False)
    def health():
        return {"ok": True}

    @app.get(f"{API}/ready", include_in_schema=False)
    def ready():
        checks = {}
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover
            checks["database"] = f"error: {type(exc).__name__}"
        if settings.redis_url:
            try:
                import redis

                redis.from_url(settings.redis_url, socket_timeout=1).ping()
                checks["redis"] = "ok"
            except Exception as exc:  # pragma: no cover
                checks["redis"] = f"error: {type(exc).__name__}"
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)

    if settings.storage_backend == "local":
        Path(settings.media_root).mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=settings.media_root), name="media")

    _otel(app)
    return app


app = create_app()
