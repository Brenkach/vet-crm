"""Демо-дані завантажуються лише в sandbox і не дублюються."""

import pytest
from sqlalchemy import func, select

from app.core.bootstrap import ensure_admin
from app.core.config import Environment, Settings
from app.models import Pet, Role, User
from app.seed import check_can_seed, seed


def cfg(env: Environment, **extra) -> Settings:
    return Settings(
        _env_file=None, app_env=env, database_url="sqlite+aiosqlite:///./x.db", secret_key="x" * 40, **extra
    )


def test_seed_refused_in_production():
    with pytest.raises(SystemExit, match="sandbox"):
        check_can_seed(cfg(Environment.PRODUCTION, seed_user_password="whatever123"))


def test_seed_requires_password_from_env():
    with pytest.raises(SystemExit, match="SEED_USER_PASSWORD"):
        check_can_seed(cfg(Environment.SANDBOX))


def test_seed_allowed_in_sandbox():
    assert check_can_seed(cfg(Environment.SANDBOX, seed_user_password="demo-pass-123")) == "demo-pass-123"


async def test_seed_is_idempotent(session_factory):
    assert await seed(session_factory, "demo-pass-123") == 2
    assert await seed(session_factory, "demo-pass-123") == 0
    async with session_factory() as session:
        assert await session.scalar(select(func.count(User.id))) == 2
        assert await session.scalar(select(func.count(Pet.id))) == 3


async def test_seeded_user_can_log_in(client, session_factory):
    await seed(session_factory, "demo-pass-123")
    resp = await client.post("/auth/login", data={"username": "ivan@sandbox.example.com", "password": "demo-pass-123"})
    assert resp.status_code == 200


async def test_bootstrap_admin_created_once(session_factory):
    assert await ensure_admin(session_factory, "Boss@Example.com", "adminpass123") is True
    assert await ensure_admin(session_factory, "boss@example.com", "adminpass123") is False
    async with session_factory() as session:
        admin = await session.scalar(select(User).where(User.email == "boss@example.com"))
        assert admin.role == Role.ADMIN
