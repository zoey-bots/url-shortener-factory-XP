"""Cryptographically random base62 short-code generation."""

from __future__ import annotations

import secrets
import string

BASE62_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7


def generate_code() -> str:
    """Return a 7 character base62 code drawn from a CSPRNG.

    ``secrets.choice`` is used so codes cannot be predicted from creation
    order, and the alphabet is exactly ``a-z``, ``A-Z`` and ``0-9``.
    """

    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(CODE_LENGTH))
