"""FR-2/FR-6/FR-7 API tests: redirects, metadata and deletion."""

from __future__ import annotations

from tests.support import AUTH, DESTINATION, assert_error, create_link


def test_redirect_returns_302_to_the_original_url(client):
    created = create_link(client).json()

    response = client.get(f"/{created['code']}")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
    assert response.content == b""


def test_unknown_code_redirects_to_json_404(client):
    response = client.get("/does-not-exist")

    assert_error(response, 404, "not_found")


def test_expired_code_returns_json_410_without_recording_a_click(client):
    created = create_link(client, expires_at="2000-01-01T00:00:00Z").json()

    redirect = client.get(f"/{created['code']}")

    assert_error(redirect, 410, "link_expired")
    stats = client.get(
        f"/api/links/{created['code']}/stats", headers=AUTH
    ).json()
    assert stats["total_clicks"] == 0


def test_expired_link_metadata_remains_readable(client):
    created = create_link(client, expires_at="2000-01-01T00:00:00Z").json()

    response = client.get(f"/api/links/{created['code']}", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == created["code"]
    assert body["url"] == DESTINATION
    assert body["expires_at"] == "2000-01-01T00:00:00+00:00"


def test_link_details_contract_and_unknown_code(client):
    created = create_link(client).json()

    found = client.get(f"/api/links/{created['code']}", headers=AUTH)
    missing = client.get("/api/links/missing", headers=AUTH)

    assert found.status_code == 200
    assert found.json() == created
    assert_error(missing, 404, "not_found")


def test_delete_returns_204_and_the_short_url_stops_working(client):
    created = create_link(client).json()
    code = created["code"]

    deleted = client.delete(f"/api/links/{code}", headers=AUTH)

    assert deleted.status_code == 204
    assert deleted.content == b""

    assert_error(client.get(f"/{code}"), 404, "not_found")
    assert_error(client.get(f"/api/links/{code}", headers=AUTH), 404, "not_found")
    assert_error(
        client.get(f"/api/links/{code}/stats", headers=AUTH), 404, "not_found"
    )
    assert_error(
        client.delete(f"/api/links/{code}", headers=AUTH), 404, "not_found"
    )


def test_delete_removes_analytics_and_a_reused_alias_starts_fresh(client):
    created = create_link(client, custom_alias="delete-me").json()
    assert created["code"] == "delete-me"

    assert client.get("/delete-me").status_code == 302
    before = client.get("/api/links/delete-me/stats", headers=AUTH).json()
    assert before["total_clicks"] == 1

    assert client.delete("/api/links/delete-me", headers=AUTH).status_code == 204

    recreated = create_link(client, custom_alias="delete-me")
    assert recreated.status_code == 201
    after = client.get("/api/links/delete-me/stats", headers=AUTH).json()

    assert after["total_clicks"] == 0
    assert after["top_referrers"] == []
    assert [entry["clicks"] for entry in after["clicks_per_day"]] == [0] * 7


def test_deleting_an_unknown_code_returns_404(client):
    response = client.delete("/api/links/missing", headers=AUTH)

    assert_error(response, 404, "not_found")


def test_delete_requires_authentication(client):
    created = create_link(client).json()

    response = client.delete(f"/api/links/{created['code']}")

    assert_error(response, 401, "unauthorized")
    assert client.get(f"/{created['code']}").status_code == 302
