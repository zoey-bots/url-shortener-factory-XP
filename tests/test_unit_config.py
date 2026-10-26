"""Configuration unit tests: exactly three env variables, fail-closed keys."""

from __future__ import annotations

from app.config import (
    DEFAULT_BASE_URL,
    DEFAULT_DATABASE_PATH,
    load_settings,
)
from app.main import create_app


def test_defaults_when_environment_is_empty():
    settings = load_settings({})

    assert settings.base_url == DEFAULT_BASE_URL == "http://localhost:8000"
    assert settings.database_path == DEFAULT_DATABASE_PATH == "./links.db"
    assert settings.api_keys == ()
    assert settings.base_hostname == "localhost"


def test_explicit_environment_values_are_used():
    settings = load_settings(
        {
            "BASE_URL": "https://sho.rt/",
            "DATABASE_PATH": "/tmp/custom.db",
            "API_KEYS": "first,second",
        }
    )

    assert settings.base_url == "https://sho.rt/"
    assert settings.database_path == "/tmp/custom.db"
    assert settings.api_keys == ("first", "second")
    assert settings.base_hostname == "sho.rt"
    assert settings.short_url_prefix == "https://sho.rt"
    assert settings.short_url("abc1234") == "https://sho.rt/abc1234"


def test_api_keys_are_trimmed_and_empty_entries_ignored():
    settings = load_settings({"API_KEYS": "  alpha , ,beta,  , gamma  "})

    assert settings.api_keys == ("alpha", "beta", "gamma")


def test_empty_or_whitespace_api_keys_fail_closed():
    assert load_settings({"API_KEYS": ""}).api_keys == ()
    assert load_settings({"API_KEYS": "   ,  , "}).api_keys == ()


def test_blank_base_url_and_database_path_fall_back_to_defaults():
    settings = load_settings({"BASE_URL": "   ", "DATABASE_PATH": ""})

    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.database_path == DEFAULT_DATABASE_PATH


def test_short_url_prefix_tolerates_trailing_slash():
    settings = load_settings({"BASE_URL": "http://localhost:8000/"})

    assert settings.short_url_prefix == "http://localhost:8000"
    assert settings.short_url("xyz") == "http://localhost:8000/xyz"


def test_unrelated_environment_variables_are_ignored():
    settings = load_settings(
        {
            "BASE_URL": "https://example.org",
            "DATABASE_PATH": "./x.db",
            "API_KEYS": "k",
            "UNRELATED_FLAG": "do-not-use",
            "PORT": "9999",
        }
    )

    assert settings.base_url == "https://example.org"
    assert settings.database_path == "./x.db"
    assert settings.api_keys == ("k",)


def test_create_app_without_settings_reads_environment_at_creation(
    monkeypatch, tmp_path
):
    database = tmp_path / "from-env.db"
    monkeypatch.setenv("BASE_URL", "https://sho.rt")
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("API_KEYS", "env-key-one,env-key-two")

    application = create_app()

    assert application.state.settings.base_url == "https://sho.rt"
    assert application.state.settings.database_path == str(database)
    assert application.state.settings.api_keys == ("env-key-one", "env-key-two")
    assert application.state.settings.base_hostname == "sho.rt"
