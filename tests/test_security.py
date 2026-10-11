"""Юніт-тести модуля безпеки (без HTTP і БД)."""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_not_stored_plain():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)


def test_wrong_password_is_rejected():
    assert not verify_password("wrong-pass", hash_password("secret123"))


def test_token_roundtrip():
    payload = decode_access_token(create_access_token("42"))
    assert payload is not None and payload["sub"] == "42"


def test_tampered_token_is_rejected():
    token = create_access_token("42")
    assert decode_access_token(token[:-2] + "xx") is None


def test_expired_token_is_rejected():
    assert decode_access_token(create_access_token("42", expires_minutes=-1)) is None
