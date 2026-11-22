"""ЛР №7: оптимізації продуктивності не ламають логіку і дають очікуваний ефект."""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest
from sqlalchemy import event, func, select

from app.core.cache import cache
from app.models import Appointment
from tests.conftest import PASSWORD


@pytest.fixture
def sql_log(session_factory):
    """Список SQL-запитів, виконаних тестовою БД."""
    statements = []
    engine = session_factory.kw["bind"].sync_engine

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine, "before_cursor_execute", record)


@pytest.fixture
def redis_cache():
    cache.client = fakeredis.FakeAsyncRedis(decode_responses=True)
    cache.hits = cache.misses = 0
    yield cache
    cache.client = None


async def add_appointment(client, headers, pet_id, days=1):
    when = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    resp = await client.post(
        "/appointments", json={"pet_id": pet_id, "scheduled_at": when, "reason": "Огляд"}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()


# ---------- Стратегія 1: менше SQL-запитів (без зайвого завантаження зв'язків) ----------
@pytest.mark.parametrize(
    "path,expected",
    [
        ("/pets", 2),  # користувач + тварини (було 3: ще й усі записи на прийом)
        ("/appointments", 2),  # користувач + записи (було 3: ще й тварини)
        ("/pets/{pet_id}", 2),  # користувач + тварина (було 3)
    ],
)
async def test_read_endpoints_query_count(client, bob_headers, bob_pet, sql_log, path, expected):
    await add_appointment(client, bob_headers, bob_pet["id"])
    sql_log.clear()
    resp = await client.get(path.format(pet_id=bob_pet["id"]), headers=bob_headers)
    assert resp.status_code == 200
    assert len(sql_log) == expected, sql_log


async def test_cancel_loads_pet_with_join(client, bob_headers, bob_appointment, sql_log):
    sql_log.clear()
    resp = await client.post(f"/appointments/{bob_appointment['id']}/cancel", headers=bob_headers)
    assert resp.status_code == 200
    selects = [s for s in sql_log if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2  # користувач + запис разом із твариною (JOIN); було 3
    assert "JOIN" in selects[1].upper()


async def test_admin_stats_single_query(client, admin_headers, bob_appointment, sql_log):
    sql_log.clear()
    resp = await client.get("/admin/stats", headers=admin_headers)
    assert resp.json() == {"users": 2, "pets": 1, "appointments": 1, "scheduled_appointments": 1}
    assert len(sql_log) == 2  # користувач + один запит статистики (було 1 + 4)


async def test_deleting_pet_deletes_its_appointments(client, bob_headers, bob_pet, session_factory):
    await add_appointment(client, bob_headers, bob_pet["id"])
    assert (await client.delete(f"/pets/{bob_pet['id']}", headers=bob_headers)).status_code == 204
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Appointment)) == 0


# ---------- Стратегія 2: bcrypt не блокує обробку інших запитів ----------
async def test_password_hashing_does_not_block_event_loop(client, alice, monkeypatch):
    """Поки рахується bcrypt (~0.25 с), цикл подій має й далі обробляти інші задачі."""
    from app.core import security

    started_at = []
    original = security.verify_password

    def timed_verify(password, hashed):
        started_at.append(time.perf_counter())
        return original(password, hashed)

    monkeypatch.setattr(security, "verify_password", timed_verify)
    noticed_after = []

    async def watcher():
        # Опитує кожну мілісекунду. Якщо bcrypt блокує цикл подій, watcher «помітить» початок
        # хешування лише після його завершення — тобто через ~0.25 с
        while not started_at:
            await asyncio.sleep(0.001)
        noticed_after.append(time.perf_counter() - started_at[0])

    async def login():
        resp = await client.post("/auth/login", data={"username": alice.email, "password": PASSWORD})
        assert resp.status_code == 200

    await asyncio.gather(login(), watcher())
    assert noticed_after[0] < 0.05, f"цикл подій був заблокований {noticed_after[0]:.3f} с"


# ---------- Стратегія 3: кеш Redis ----------
async def test_pets_list_is_cached(client, bob_headers, bob_pet, redis_cache, sql_log):
    first = await client.get("/pets", headers=bob_headers)
    assert first.headers["X-Cache"] == "MISS"
    sql_log.clear()
    second = await client.get("/pets", headers=bob_headers)
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    assert sql_log == []  # і користувач, і тварини — з кешу, БД не задіяна


@pytest.mark.parametrize("action", ["create", "update", "delete"])
async def test_pets_cache_invalidated_on_change(client, bob_headers, bob_pet, redis_cache, action):
    await client.get("/pets", headers=bob_headers)  # наповнюємо кеш
    if action == "create":
        await client.post("/pets", json={"name": "Мурка", "species": "кіт"}, headers=bob_headers)
        expected = ["Рекс", "Мурка"]
    elif action == "update":
        await client.patch(f"/pets/{bob_pet['id']}", json={"name": "Рексик"}, headers=bob_headers)
        expected = ["Рексик"]
    else:
        await client.delete(f"/pets/{bob_pet['id']}", headers=bob_headers)
        expected = []
    resp = await client.get("/pets", headers=bob_headers)
    assert resp.headers["X-Cache"] == "MISS"
    assert [p["name"] for p in resp.json()] == expected


async def test_admin_change_to_others_pet_invalidates_owner_cache(
    client, admin_headers, bob_headers, bob_pet, redis_cache
):
    await client.get("/pets", headers=bob_headers)
    await client.patch(f"/pets/{bob_pet['id']}", json={"name": "Змінив адмін"}, headers=admin_headers)
    assert (await client.get("/pets", headers=bob_headers)).json()[0]["name"] == "Змінив адмін"


async def test_cached_user_sees_role_change_immediately(client, admin_headers, alice, alice_headers, redis_cache):
    assert (await client.get("/admin/users", headers=alice_headers)).status_code == 403  # профіль у кеші
    await client.patch(f"/admin/users/{alice.id}/role", json={"role": "admin"}, headers=admin_headers)
    assert (await client.get("/admin/users", headers=alice_headers)).status_code == 200


async def test_cached_user_sees_profile_update(client, alice, alice_headers, redis_cache):
    await client.get("/users/me", headers=alice_headers)
    await client.patch(f"/users/{alice.id}", json={"full_name": "Аліса"}, headers=alice_headers)
    assert (await client.get("/users/me", headers=alice_headers)).json()["full_name"] == "Аліса"


async def test_password_hash_not_stored_in_cache(client, alice_headers, redis_cache):
    await client.get("/users/me", headers=alice_headers)
    values = [await redis_cache.client.get(k) for k in await redis_cache.client.keys("*")]
    assert values and not any("hashed_password" in v or "$2b$" in v for v in values)


async def test_admin_stats_cached_with_ttl(client, admin_headers, bob_pet, redis_cache):
    assert (await client.get("/admin/stats", headers=admin_headers)).headers["X-Cache"] == "MISS"
    assert (await client.get("/admin/stats", headers=admin_headers)).headers["X-Cache"] == "HIT"
    assert 0 < await redis_cache.client.ttl("vetcrm:admin:stats") <= 10


async def test_cache_keys_have_ttl(client, bob_headers, bob_pet, redis_cache):
    await client.get("/pets", headers=bob_headers)
    for key in await redis_cache.client.keys("*"):
        assert await redis_cache.client.ttl(key) > 0, key


async def test_app_works_when_redis_is_down(client, bob_headers, bob_pet, caplog):
    import redis.asyncio as redis

    cache.client = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    try:
        resp = await client.get("/pets", headers=bob_headers)
        assert resp.status_code == 200 and resp.json()[0]["name"] == "Рекс"
        assert "Redis недоступний" in caplog.text
    finally:
        await cache.client.aclose()
        cache.client = None
        cache._down_until = 0.0
