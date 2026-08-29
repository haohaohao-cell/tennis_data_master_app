from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.staticfiles import StaticFiles

from backend.app.admin.router import router as admin_router
from backend.app.auth.router import router as auth_router
from backend.app.core.config import settings
from backend.app.core.database import get_connection, initialize_database
from backend.app.locations.service import warm_location_resolver_cache
from backend.app.locations.router import router as locations_router
from backend.app.messages.router import router as messages_router
from backend.app.posts.router import router as posts_router
from backend.app.privacy.router import router as privacy_router
from backend.app.profile.router import router as profile_router
from backend.app.reports.router import router as reports_router
from backend.app.social.router import router as social_router
from backend.app.uploads.router import router as uploads_router
from backend.app.users.router import router as users_router


logger = logging.getLogger("backend.request")
startup_logger = logging.getLogger("backend.startup")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    started_at = time.perf_counter()
    warm_location_resolver_cache()
    startup_logger.info(
        "location resolver warmed in %sms",
        round((time.perf_counter() - started_at) * 1000, 1),
    )
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def request_id_and_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started_at = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
    except Exception as error:
        status_code = 500
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.exception(
            "request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "status_code": status_code,
            },
        )
        detail_message = "Internal server error."
        if settings.is_development:
            detail_message = f"{error.__class__.__name__}: {error}"
        response = JSONResponse(
            status_code=status_code,
            content={
                "detail": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": detail_message,
                }
            },
        )
    finally:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        status_code = getattr(response, "status_code", 500)
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            status_code,
            extra={
                "request_id": request_id,
                "duration_ms": duration_ms,
                "status_code": status_code,
            },
        )
        # Cancellation can interrupt ``call_next`` before it creates a response.
        # Keep the original cancellation/error intact instead of masking it with
        # a secondary ``None.headers`` failure in the middleware cleanup path.
        if response is not None:
            response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    response = JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )
    response.headers["X-Request-ID"] = request_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(locations_router, prefix=settings.api_prefix)
app.include_router(uploads_router, prefix=settings.api_prefix)
app.include_router(posts_router, prefix=settings.api_prefix)
app.include_router(profile_router, prefix=settings.api_prefix)
app.include_router(social_router, prefix=settings.api_prefix)
app.include_router(messages_router, prefix=settings.api_prefix)
app.include_router(privacy_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)

settings.video_storage_dir.mkdir(parents=True, exist_ok=True)
settings.message_media_storage_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.public_video_path_prefix,
    StaticFiles(directory=settings.video_storage_dir, check_dir=False),
    name="video-storage",
)
settings.avatar_storage_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.public_avatar_path_prefix,
    StaticFiles(directory=settings.avatar_storage_dir, check_dir=False),
    name="avatar-storage",
)


@app.get("/health")
def health() -> dict[str, str]:
    database_status = "ok"
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1;").fetchone()
    except Exception:
        database_status = "unavailable"
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "environment": settings.environment,
        "database": database_status,
    }
