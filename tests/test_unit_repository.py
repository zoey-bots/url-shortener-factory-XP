"""Repository unit tests: creation, deletion, expiry, clicks and analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import links
from app.db import Database
from app.errors import ApiError
from app.links import LinkRepository, normalize_referrer
from tests.support import BASE_URL, DESTINATION


@pytest.fixture
def repo(tmp_path) -> LinkRepository:
    database = Database(str(tmp_path / "links.db"))
    database.initialize()
    return LinkRepository(database, BASE_URL)


def test_create_returns_serialised_link(repo):
    link = repo.create(DESTINATION)

    assert set(link) == {"code", "short_url", "url", "created_at", "expires_at"}
    assert len(link["code"]) == 7
    assert link["url"] == DESTINATION
    assert link["short_url"] == f"{BASE_URL}/{link['code']}"
    assert link["expires_at"] is None
    created_at = datetime.fromisoformat(link["created_at"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() == timedelta(0)


def test_create_uses_supplied_clock(repo):
    now = datetime(2026, 4, 5, 6, 7, 8, tzinfo=timezone.utc)

    link = repo.create(DESTINATION, now=now)

    assert link["created_at"] == now.isoformat()


def test_custom_alias_is_honoured_exactly(repo):
    link = repo.create(DESTINATION, custom_alias="My_alias-1")

    assert link["code"] == "My_alias-1"
    assert repo.get("My_alias-1") == link


def test_duplicate_url_without_alias_creates_independent_codes(repo):
    first = repo.create(DESTINATION)
    second = repo.create(DESTINATION)

    assert first["code"] != second["code"]
    assert first["url"] == second["url"] == DESTINATION


def test_taken_alias_conflicts_and_keeps_the_original(repo):
    original = repo.create("https://example.com/first", custom_alias="taken-1")

    with pytest.raises(ApiError) as excinfo:
        repo.create("https://example.com/second", custom_alias="taken-1")

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "alias_taken"
    assert repo.get("taken-1")["url"] == original["url"]


def test_random_code_collisions_are_retried_then_fail_cleanly(
    repo, monkeypatch
):
    calls = {"count": 0}

    def fixed_code() -> str:
        calls["count"] += 1
        return "FIXED01"

    monkeypatch.setattr(links, "generate_code", fixed_code)

    original = repo.create("https://example.com/first")
    with pytest.raises(ApiError) as excinfo:
        repo.create("https://example.com/second")

    assert excinfo.value.status_code == 500
    assert excinfo.value.code == "code_generation_failed"
    assert calls["count"] == links.MAX_CODE_ATTEMPTS + 1
    assert repo.get("FIXED01") == original


def test_get_returns_none_for_unknown_code(repo):
    assert repo.get("missing") is None


def test_delete_reports_whether_a_link_existed(repo):
    repo.create(DESTINATION, custom_alias="gone")

    assert repo.delete("gone") is True
    assert repo.get("gone") is None
    assert repo.delete("gone") is False


def test_resolve_records_one_click_per_successful_redirect(repo):
    link = repo.create(DESTINATION)
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    resolved, status_code = repo.resolve(link["code"], "https://ref.example", now)
    assert status_code == 302
    assert resolved["url"] == DESTINATION

    repo.resolve(link["code"], "https://ref.example", now)
    stats = repo.stats(link["code"], now=now)

    assert stats["total_clicks"] == 2
    assert stats["top_referrers"] == [
        {"referrer": "https://ref.example", "clicks": 2}
    ]


def test_resolve_unknown_code_returns_404_without_click(repo):
    resolved, status_code = repo.resolve("missing", "direct")

    assert resolved is None
    assert status_code == 404


def test_expired_link_returns_410_and_records_no_click(repo):
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    link = repo.create(
        DESTINATION,
        expires_at=(now + timedelta(hours=1)).isoformat(),
        now=now,
    )

    _, status_before = repo.resolve(link["code"], "direct", now + timedelta(minutes=30))
    expired_link, status_after = repo.resolve(
        link["code"], "direct", now + timedelta(hours=2)
    )

    assert status_before == 302
    assert status_after == 410
    assert expired_link["code"] == link["code"]
    assert repo.get(link["code"]) is not None
    assert repo.stats(link["code"], now=now + timedelta(hours=2))[
        "total_clicks"
    ] == 1


def test_stats_unknown_code_is_none(repo):
    assert repo.stats("missing") is None


def test_stats_zero_fills_exactly_seven_utc_days(repo):
    now = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    link = repo.create(DESTINATION, now=now)

    stats = repo.stats(link["code"], now=now)

    assert stats["total_clicks"] == 0
    assert stats["top_referrers"] == []
    assert [entry["clicks"] for entry in stats["clicks_per_day"]] == [0] * 7

    dates = [
        datetime.fromisoformat(entry["date"]).date()
        for entry in stats["clicks_per_day"]
    ]
    expected = [(now - timedelta(days=6 - index)).date() for index in range(7)]
    assert dates == expected


def test_stats_use_last_seven_days_but_total_counts_all_time(repo):
    now = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    link = repo.create(DESTINATION, now=now - timedelta(days=30))

    for offset, referrer in ((7, "r7"), (6, "r6"), (1, "r1"), (0, "r0")):
        repo.resolve(link["code"], referrer, now=now - timedelta(days=offset))

    stats = repo.stats(link["code"], now=now)
    counts = [entry["clicks"] for entry in stats["clicks_per_day"]]

    assert stats["total_clicks"] == 4
    assert counts == [1, 0, 0, 0, 0, 1, 1]


def test_stats_top_five_referrers_descending_with_direct_bucket(repo):
    now = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    link = repo.create(DESTINATION, now=now)

    for referrer, clicks in (
        ("a", 6),
        ("b", 5),
        ("c", 4),
        ("d", 3),
        ("e", 2),
        ("f", 1),
    ):
        for _ in range(clicks):
            repo.resolve(link["code"], referrer, now=now)

    stats = repo.stats(link["code"], now=now)

    assert stats["total_clicks"] == 21
    assert stats["top_referrers"] == [
        {"referrer": "a", "clicks": 6},
        {"referrer": "b", "clicks": 5},
        {"referrer": "c", "clicks": 4},
        {"referrer": "d", "clicks": 3},
        {"referrer": "e", "clicks": 2},
    ]


def test_delete_removes_clicks_so_a_reused_alias_starts_fresh(repo):
    now = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    link = repo.create(DESTINATION, custom_alias="reuse-me", now=now)
    repo.resolve(link["code"], "direct", now=now)

    assert repo.delete("reuse-me") is True
    assert repo.stats("reuse-me", now=now) is None

    recreated = repo.create(DESTINATION, custom_alias="reuse-me", now=now)
    fresh_stats = repo.stats(recreated["code"], now=now)

    assert fresh_stats["total_clicks"] == 0
    assert fresh_stats["top_referrers"] == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "direct"),
        ("", "direct"),
        ("   ", "direct"),
        (" https://ref.example ", "https://ref.example"),
        ("https://ref.example/path", "https://ref.example/path"),
    ],
)
def test_normalize_referrer_buckets_missing_and_blank_as_direct(
    value, expected
):
    assert normalize_referrer(value) == expected
