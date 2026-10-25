"""Вертикальне розмежування: звичайний користувач не має доступу до адмін-функцій."""

import pytest

ADMIN_ONLY = [
    ("GET", "/admin/users", None),
    ("GET", "/admin/stats", None),
    ("GET", "/home/admin", None),
]


@pytest.mark.parametrize("method,url,json", ADMIN_ONLY)
async def test_client_forbidden_in_admin_panel(client, alice_headers, method, url, json):
    resp = await client.request(method, url, json=json, headers=alice_headers)
    assert resp.status_code == 403


@pytest.mark.parametrize("method,url,json", ADMIN_ONLY)
async def test_admin_allowed_in_admin_panel(client, admin_headers, method, url, json):
    resp = await client.request(method, url, json=json, headers=admin_headers)
    assert resp.status_code == 200


async def test_client_cannot_promote_self(client, alice, alice_headers):
    resp = await client.patch(f"/admin/users/{alice.id}/role", json={"role": "admin"}, headers=alice_headers)
    assert resp.status_code == 403
    me = await client.get("/users/me", headers=alice_headers)
    assert me.json()["role"] == "client"


async def test_client_cannot_change_appointment_status(client, bob_headers, bob_appointment):
    resp = await client.patch(
        f"/appointments/{bob_appointment['id']}/status", json={"status": "completed"}, headers=bob_headers
    )
    assert resp.status_code == 403


async def test_admin_can_change_appointment_status(client, admin_headers, bob_appointment):
    resp = await client.patch(
        f"/appointments/{bob_appointment['id']}/status", json={"status": "completed"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_role_change_takes_effect_immediately(client, admin_headers, alice, alice_headers):
    resp = await client.patch(f"/admin/users/{alice.id}/role", json={"role": "admin"}, headers=admin_headers)
    assert resp.status_code == 200
    # той самий старий токен — але роль читається з БД
    assert (await client.get("/admin/users", headers=alice_headers)).status_code == 200


async def test_home_pages_by_role(client, admin_headers, alice_headers):
    assert (await client.get("/home", headers=admin_headers)).json()["role"] == "admin"
    assert (await client.get("/home", headers=alice_headers)).json()["role"] == "client"
    assert (await client.get("/home/client", headers=alice_headers)).status_code == 200
    assert (await client.get("/home/client", headers=admin_headers)).status_code == 403
