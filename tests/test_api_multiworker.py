"""Non-functional tests: several workers/share one SQLite file safely."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.db import Database
from app.errors import ApiError
from app.links import LinkRepository
from app.main import create_app
from tests.support import (
    API_KEY,
    AUTH,
    BASE_URL,
    DESTINATION,
    assert_error,
    create_link,
    make_settings,
)


def test_two_applications_share_links_and_clicks(tmp_path):
    settings = make_settings(tmp_path / "shared.db", api_keys=(API_KEY,))

    with (
        TestClient(create_app(settings), follow_redirects=False) as first,
        TestClient(create_app(settings), follow_redirects=False) as second,
    ):
        created = create_link(first).json()
        code = created["code"]

        metadata = second.get(f"/api/links/{code}", headers=AUTH)
        assert metadata.status_code == 200
        assert metadata.json()["url"] == DESTINATION

        assert second.get(f"/{code}").status_code == 302

        stats = first.get(f"/api/links/{code}/stats", headers=AUTH).json()
        assert stats["total_clicks"] == 1


def test_restart_preserves_links_and_clicks(tmp_path):
    settings = make_settings(tmp_path / "restart.db", api_keys=(API_KEY,))

    with TestClient(create_app(settings), follow_redirects=False) as first:
        created = create_link(first).json()
        code = created["code"]
        assert first.get(f"/{code}").status_code == 302

    with TestClient(create_app(settings), follow_redirects=False) as second:
        assert second.get(f"/{code}").status_code == 302
        metadata = second.get(f"/api/links/{code}", headers=AUTH)
        assert metadata.status_code == 200
        assert metadata.json()["url"] == DESTINATION
        stats = second.get(f"/api/links/{code}/stats", headers=AUTH).json()
        assert stats["total_clicks"] == 2


def test_only_one_worker_can_claim_a_custom_alias(tmp_path):
    path = str(tmp_path / "race.db")
    databases = [Database(path) for _ in range(10)]
    for database in databases:
        database.initialize()
    repositories = [LinkRepository(database, BASE_URL) for database in databases]

    def attempt(repository: LinkRepository) -> str:
        try:
            repository.create(DESTINATION, custom_alias="race-alias")
        except ApiError as exc:
            assert exc.status_code == 409
            assert exc.code == "alias_taken"
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(attempt, repositories))

    assert outcomes.count("created") == 1
    assert outcomes.count("conflict") == 9
    assert repositories[0].get("race-alias")["url"] == DESTINATION


def test_deletions_and_redirects_use_consistent_transactions(tmp_path):
    settings = make_settings(tmp_path / "delete-race.db", api_keys=(API_KEY,))

    with TestClient(create_app(settings), follow_redirects=False) as client:
        created = create_link(client).json()
        code = created["code"]

        assert client.delete(f"/api/links/{code}", headers=AUTH).status_code == 204
        assert_error(client.get(f"/{code}"), 404, "not_found")
        assert_error(
            client.get(f"/api/links/{code}/stats", headers=AUTH), 404, "not_found"
        )
