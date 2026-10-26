"""FR-3 unit tests: cryptographic, base62, seven-character codes."""

from __future__ import annotations

import string

from app import codes

BASE62 = set(string.ascii_letters + string.digits)


def test_generated_code_is_seven_base62_characters():
    code = codes.generate_code()

    assert len(code) == 7
    assert set(code) <= BASE62
    assert code.isalnum()


def test_generated_codes_are_unique_across_many_draws():
    samples = {codes.generate_code() for _ in range(2_000)}

    # A collision here would need ~1 in 10^9 luck for 62**7 keys.
    assert len(samples) == 2_000


def test_alphabet_is_exactly_lower_upper_digit():
    assert codes.BASE62_ALPHABET == string.ascii_letters + string.digits
    assert codes.CODE_LENGTH == 7


def test_generation_draws_from_csprng_secrets(monkeypatch):
    calls: list[str] = []

    def fake_choice(alphabet: str) -> str:
        calls.append(alphabet)
        return "Z"

    monkeypatch.setattr(codes.secrets, "choice", fake_choice)

    assert codes.generate_code() == "ZZZZZZZ"
    assert len(calls) == 7
    assert all(alphabet == codes.BASE62_ALPHABET for alphabet in calls)
