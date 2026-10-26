"""FR-8 unit tests: API-key paths, hashing and constant-time authentication."""

from __future__ import annotations

from app.auth import authenticate, hash_key, is_api_path
from tests.support import API_KEY, SECOND_API_KEY, make_settings


def test_api_path_detection_matches_only_the_api_surface():
    assert is_api_path("/api")
    assert is_api_path("/api/")
    assert is_api_path("/api/links")
    assert is_api_path("/api/anything/deep")

    assert not is_api_path("/")
    assert not is_api_path("/apix")
    assert not is_api_path("/health")
    assert not is_api_path("/API/links")
    assert not is_api_path("/abc1234")


def test_hash_key_is_stable_sha256_and_never_the_raw_key():
    digest = hash_key("secret-value")

    assert digest == hash_key("secret-value")
    assert len(digest) == 64
    assert int(digest, 16) >= 0
    assert digest != "secret-value"
    assert "secret-value" not in digest


def test_authenticate_accepts_every_configured_key(tmp_path):
    settings = make_settings(
        tmp_path / "links.db", api_keys=(API_KEY, SECOND_API_KEY)
    )

    assert authenticate(settings, API_KEY) == hash_key(API_KEY)
    assert authenticate(settings, SECOND_API_KEY) == hash_key(SECOND_API_KEY)


def test_authenticate_rejects_missing_invalid_and_blank_keys(tmp_path):
    settings = make_settings(tmp_path / "links.db")

    assert authenticate(settings, None) is None
    assert authenticate(settings, "") is None
    assert authenticate(settings, "wrong-key") is None
    assert authenticate(settings, API_KEY + " ") is None


def test_empty_key_configuration_fails_closed(tmp_path):
    settings = make_settings(tmp_path / "links.db", api_keys=())

    assert authenticate(settings, API_KEY) is None
    assert authenticate(settings, "") is None
