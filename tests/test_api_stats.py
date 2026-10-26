"""FR-9 API tests: click recording, seven-day series and top referrers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from tests.support import AUTH, DESTINATION, assert_error, create_link


def _hit(client, code: str, referrer: str | None = None):
    headers = {} if referrer is None else {"Referer": referrer}
    return client.get(f"/{code}", headers=headers)


def _stats(client, code: str) -> dict:
    return client.get(f"/api/links/{code}/stats", headers=AUTH).json()


def test_stats_shape_is_zero_filled_for_a_new_link(client):
    created = create_link(client).json()

    stats = _stats(client, created["code"])

    assert set(stats) == {"total_clicks", "clicks_per_day", "top_referrers"}
    assert stats["total_clicks"] == 0
    assert stats["top_referrers"] == []
    assert len(stats["clicks_per_day"]) == 7

    dates = []
    for entry in stats["clicks_per_day"]:
        assert set(entry) == {"date", "clicks"}
        assert entry["clicks"] == 0
        dates.append(date.fromisoformat(entry["date"]))

    assert dates == sorted(dates)
    for earlier, later in zip(dates, dates[1:]):
        assert later - earlier == timedelta(days=1)


def test_each_successful_redirect_is_recorded_exactly_once(client):
    created = create_link(client).json()
    code = created["code"]

    for _ in range(3):
        assert _hit(client, code).status_code == 302

    stats = _stats(client, code)

    assert stats["total_clicks"] == 3
    assert sum(entry["clicks"] for entry in stats["clicks_per_day"]) == 3
    assert stats["top_referrers"] == [{"referrer": "direct", "clicks": 3}]


def test_missing_and_present_referrers_are_bucketed(client):
    created = create_link(client).json()
    code = created["code"]

    _hit(client, code)
    _hit(client, code)
    _hit(client, code, "https://ref.example/page")

    stats = _stats(client, code)

    assert stats["top_referrers"] == [
        {"referrer": "direct", "clicks": 2},
        {"referrer": "https://ref.example/page", "clicks": 1},
    ]


def test_top_five_referrers_are_ordered_and_capped(client):
    created = create_link(client).json()
    code = created["code"]

    for referrer, clicks in (
        ("https://a.example", 6),
        ("https://b.example", 5),
        ("https://c.example", 4),
        ("https://d.example", 3),
        ("https://e.example", 2),
        ("https://f.example", 1),
    ):
        for _ in range(clicks):
            assert _hit(client, code, referrer).status_code == 302

    stats = _stats(client, code)

    assert stats["total_clicks"] == 21
    assert stats["top_referrers"] == [
        {"referrer": "https://a.example", "clicks": 6},
        {"referrer": "https://b.example", "clicks": 5},
        {"referrer": "https://c.example", "clicks": 4},
        {"referrer": "https://d.example", "clicks": 3},
        {"referrer": "https://e.example", "clicks": 2},
    ]


def test_clicks_per_day_covers_the_last_seven_utc_days_ascending(client):
    created = create_link(client).json()
    code = created["code"]

    for _ in range(4):
        assert _hit(client, code).status_code == 302

    stats = _stats(client, code)
    dates = [date.fromisoformat(item["date"]) for item in stats["clicks_per_day"]]

    today = datetime.now(timezone.utc).date()
    assert len(dates) == 7
    assert dates[-1] in {today, today - timedelta(days=1)}
    assert dates == [dates[-1] - timedelta(days=6 - index) for index in range(7)]
    assert sum(item["clicks"] for item in stats["clicks_per_day"]) == 4


def test_expired_link_stats_are_still_available(client):
    created = create_link(client, expires_at="2000-01-01T00:00:00Z").json()

    response = client.get(f"/api/links/{created['code']}/stats", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["total_clicks"] == 0


def test_stats_require_authentication(client):
    created = create_link(client).json()

    response = client.get(f"/api/links/{created['code']}/stats")

    assert_error(response, 401, "unauthorized")


def test_stats_are_isolated_per_link_even_with_the_same_url(client):
    first = create_link(client, url=DESTINATION).json()
    second = create_link(client, url=DESTINATION).json()

    _hit(client, first["code"])
    _hit(client, first["code"])

    assert _stats(client, first["code"])["total_clicks"] == 2
    assert _stats(client, second["code"])["total_clicks"] == 0
