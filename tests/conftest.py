"""Pytest fixtures: isolated settings, applications and HTTP clients.

``app.main`` builds a module-level application from the process environment
at import time.  Tests therefore never rely on that module-level object:
each test constructs ``create_app(settings)`` with an explicit temporary
database, and enters ``TestClient`` as a context manager so the lifespan
startup hook (schema creation) runs and is shut down deterministically.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from tests.support import API_KEY, BASE_URL, make_settings


@pytest.fixture
def settings(tmp_path):
    """Settings pointing at a fresh database inside pytest's tmp_path."""

    return make_settings(tmp_path / "links.db")


@pytest.fixture
def app(settings) -> FastAPI:
    """An application instance whose lifespan has not been entered yet."""

    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A live TestClient with lifespan entered and redirects disabled."""

    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def client_factory(
    tmp_path,
) -> Iterator[Callable[..., TestClient]]:
    """Build extra isolated clients (other key sets, shared databases)."""

    with contextlib.ExitStack() as stack:

        def factory(
            *,
            api_keys: tuple[str, ...] = (API_KEY,),
            base_url: str = BASE_URL,
            database_name: str = "links.db",
        ) -> TestClient:
            application = create_app(
                make_settings(
                    tmp_path / database_name,
                    base_url=base_url,
                    api_keys=api_keys,
                )
            )
            return stack.enter_context(
                TestClient(application, follow_redirects=False)
            )

        yield factory
