"""Request models with strict typing and field validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from .urls import parse_expires_at, validate_alias, validate_url


class CreateLinkRequest(BaseModel):
    """Body of ``POST /api/links``.

    Strict mode means JSON numbers, booleans, objects or arrays are never
    coerced into strings.  Extra properties are ignored for forward
    compatibility.
    """

    model_config = ConfigDict(strict=True, extra="ignore")

    url: str
    custom_alias: str | None = None
    expires_at: str | None = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return validate_url(value)

    @field_validator("custom_alias")
    @classmethod
    def _check_alias(cls, value: str | None) -> str | None:
        if value is None:
            # Omitted fields never reach this validator; an explicit JSON
            # ``null`` does, and is rejected instead of being coerced.
            raise ValueError("must be a string when provided")
        return validate_alias(value)

    @field_validator("expires_at")
    @classmethod
    def _check_expiry(cls, value: str | None) -> str | None:
        if value is None:
            # Omitted fields never reach this validator; an explicit JSON
            # ``null`` does, and is rejected instead of being coerced.
            raise ValueError("must be a string when provided")
        return parse_expires_at(value).isoformat()
