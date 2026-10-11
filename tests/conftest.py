"""Спільні фікстури: окрема БД у пам'яті для кожного тесту, HTTP-клієнт, користувачі різних ролей."""

from datetime import datetime, timedelta, timezone
from typing import Dict

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.database import Base, get_session
from app.main import app
from app.models import Role, User

PASSWORD = "password123"


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # одне з'єднання — інакше кожне бачило б свою порожню БД
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(session_factory):
    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(session_factory, email: str, role: Role) -> User:
    async with session_factory() as session:
        user = User(
            email=email,
            full_name=email.split("@")[0],
            hashed_password=hash_password(PASSWORD),
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Dict[str, str]:
    resp = await client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def admin(session_factory):
    return await _create_user(session_factory, "admin@example.com", Role.ADMIN)


@pytest.fixture
async def alice(session_factory):
    return await _create_user(session_factory, "alice@example.com", Role.CLIENT)


@pytest.fixture
async def bob(session_factory):
    return await _create_user(session_factory, "bob@example.com", Role.CLIENT)


@pytest.fixture
async def admin_headers(client, admin):
    return await login(client, admin.email)


@pytest.fixture
async def alice_headers(client, alice):
    return await login(client, alice.email)


@pytest.fixture
async def bob_headers(client, bob):
    return await login(client, bob.email)


@pytest.fixture
async def bob_pet(client, bob_headers):
    resp = await client.post("/pets", json={"name": "Рекс", "species": "собака"}, headers=bob_headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
async def bob_appointment(client, bob_headers, bob_pet):
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resp = await client.post(
        "/appointments",
        json={"pet_id": bob_pet["id"], "scheduled_at": when, "reason": "Щеплення"},
        headers=bob_headers,
    )
    assert resp.status_code == 201
    return resp.json()
