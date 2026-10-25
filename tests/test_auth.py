"""Анонімний доступ, реєстрація, успішний вхід і помилки входу."""

import pytest

from app.core.security import create_access_token
from tests.conftest import PASSWORD, login

PROTECTED = [
    ("GET", "/users/me"),
    ("GET", "/home"),
    ("GET", "/home/admin"),
    ("GET", "/pets"),
    ("GET", "/appointments"),
    ("GET", "/admin/users"),
]


# ---------- Анонімний доступ ----------
@pytest.mark.parametrize("method,url", PROTECTED)
async def test_anonymous_gets_401(client, method, url):
    resp = await client.request(method, url)
    assert resp.status_code == 401


async def test_invalid_token_gets_401(client):
    resp = await client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


async def test_token_of_deleted_user_gets_401(client):
    token = create_access_token("9999")
    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ---------- Реєстрація ----------
async def test_register_creates_client(client):
    resp = await client.post(
        "/auth/register", json={"email": "new@example.com", "full_name": "Новий", "password": PASSWORD}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "client"
    assert "password" not in body and "hashed_password" not in body


async def test_register_cannot_choose_admin_role(client):
    resp = await client.post(
        "/auth/register", json={"email": "hacker@example.com", "full_name": "H", "password": PASSWORD, "role": "admin"}
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "client"


async def test_register_duplicate_email(client, alice):
    resp = await client.post("/auth/register", json={"email": alice.email, "full_name": "Copy", "password": PASSWORD})
    assert resp.status_code == 409


async def test_register_short_password(client):
    resp = await client.post("/auth/register", json={"email": "x@example.com", "full_name": "X", "password": "123"})
    assert resp.status_code == 422


# ---------- Вхід ----------
async def test_register_then_login_then_access(client):
    await client.post("/auth/register", json={"email": "flow@example.com", "full_name": "Flow", "password": PASSWORD})
    headers = await login(client, "flow@example.com")
    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "flow@example.com"


async def test_admin_can_login(client, admin):
    headers = await login(client, admin.email)
    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_login_wrong_password(client, alice):
    resp = await client.post("/auth/login", data={"username": alice.email, "password": "wrong-password"})
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


async def test_login_unknown_email(client):
    resp = await client.post("/auth/login", data={"username": "ghost@example.com", "password": PASSWORD})
    assert resp.status_code == 401
