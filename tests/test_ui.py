"""Веб-інтерфейс віддається сервером; доступ до даних усе одно контролює API."""

import pytest


async def test_root_redirects_to_ui(client):
    resp = await client.get("/")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/ui/"


@pytest.mark.parametrize("page", ["index.html", "login.html", "register.html", "client.html", "admin.html"])
async def test_ui_pages_are_served(client, page):
    resp = await client.get(f"/ui/{page}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_admin_page_is_public_but_admin_data_is_not(client, alice_headers):
    # Сама сторінка — лише HTML-оболонка; дані адмінки клієнту не віддаються
    assert (await client.get("/ui/admin.html")).status_code == 200
    assert (await client.get("/admin/users", headers=alice_headers)).status_code == 403
