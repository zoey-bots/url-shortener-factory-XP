"""FastAPI application factory and process entry point.

``uvicorn app.main:app --port 8000`` starts the service.  Configuration
is read from the environment when the module's ``app`` is created; set
``BASE_URL``, ``DATABASE_PATH`` and ``API_KEYS`` beforehand.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from . import auth
from .api import router as api_router
from .config import Settings, load_settings
from .db import Database
from .errors import error_response, install_error_handlers
from .links import LinkRepository
from .redirect import router as public_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance bound to ``settings``."""

    resolved = settings or load_settings()
    database = Database(resolved.database_path)
    repository = LinkRepository(database, resolved.base_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        yield

    application = FastAPI(
        title="URL Shortener",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved
    application.state.db = database
    application.state.repository = repository

    @application.middleware("http")
    async def authenticate_api_requests(request: Request, call_next):
        """Protect every ``/api/*`` path before routing or body parsing."""

        if auth.is_api_path(request.url.path):
            key_hash = auth.authenticate(
                resolved, request.headers.get("x-api-key")
            )
            if key_hash is None:
                return error_response(
                    401, "unauthorized", "Missing or invalid API key."
                )
        return await call_next(request)

    install_error_handlers(application)
    application.include_router(api_router)
    application.include_router(public_router)
    return application


app = create_app()
