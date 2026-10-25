"""Горизонтальне розмежування (IDOR): користувач не може читати/змінювати чужі дані."""

from datetime import datetime, timedelta, timezone


# ---------- Профіль іншого користувача ----------
async def test_cannot_update_other_user_profile(client, alice_headers, bob, bob_headers):
    resp = await client.patch(f"/users/{bob.id}", json={"full_name": "Зламано"}, headers=alice_headers)
    assert resp.status_code == 403
    assert (await client.get("/users/me", headers=bob_headers)).json()["full_name"] == "bob"


async def test_cannot_change_other_user_password(client, alice_headers, bob):
    resp = await client.patch(f"/users/{bob.id}", json={"password": "newpassword1"}, headers=alice_headers)
    assert resp.status_code == 403
    login = await client.post("/auth/login", data={"username": bob.email, "password": "newpassword1"})
    assert login.status_code == 401


async def test_cannot_read_other_user_profile(client, alice_headers, bob):
    assert (await client.get(f"/users/{bob.id}", headers=alice_headers)).status_code == 403


async def test_can_update_own_profile(client, alice, alice_headers):
    resp = await client.patch(f"/users/{alice.id}", json={"full_name": "Аліса"}, headers=alice_headers)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Аліса"


# ---------- Чужа тварина ----------
async def test_cannot_read_other_pet(client, alice_headers, bob_pet):
    assert (await client.get(f"/pets/{bob_pet['id']}", headers=alice_headers)).status_code == 403


async def test_cannot_update_other_pet(client, alice_headers, bob_headers, bob_pet):
    resp = await client.patch(f"/pets/{bob_pet['id']}", json={"name": "Чужий"}, headers=alice_headers)
    assert resp.status_code == 403
    unchanged = await client.get(f"/pets/{bob_pet['id']}", headers=bob_headers)
    assert unchanged.json()["name"] == "Рекс"


async def test_cannot_delete_other_pet(client, alice_headers, bob_headers, bob_pet):
    assert (await client.delete(f"/pets/{bob_pet['id']}", headers=alice_headers)).status_code == 403
    assert (await client.get(f"/pets/{bob_pet['id']}", headers=bob_headers)).status_code == 200


async def test_pet_list_shows_only_own(client, alice_headers, bob_pet):
    await client.post("/pets", json={"name": "Мурка", "species": "кіт"}, headers=alice_headers)
    pets = (await client.get("/pets", headers=alice_headers)).json()
    assert [p["name"] for p in pets] == ["Мурка"]


async def test_admin_can_access_any_pet(client, admin_headers, bob_pet):
    assert (await client.get(f"/pets/{bob_pet['id']}", headers=admin_headers)).status_code == 200


# ---------- Чужі записи на прийом ----------
async def test_cannot_book_appointment_for_other_pet(client, alice_headers, bob_pet):
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = await client.post(
        "/appointments", json={"pet_id": bob_pet["id"], "scheduled_at": when, "reason": "?"}, headers=alice_headers
    )
    assert resp.status_code == 403


async def test_cannot_cancel_other_appointment(client, alice_headers, bob_headers, bob_appointment):
    resp = await client.post(f"/appointments/{bob_appointment['id']}/cancel", headers=alice_headers)
    assert resp.status_code == 403
    still = await client.get(f"/appointments/{bob_appointment['id']}", headers=bob_headers)
    assert still.json()["status"] == "scheduled"


async def test_cannot_read_other_appointment(client, alice_headers, bob_appointment):
    assert (await client.get(f"/appointments/{bob_appointment['id']}", headers=alice_headers)).status_code == 403


async def test_nonexistent_resource_is_404_not_403(client, alice_headers):
    assert (await client.get("/pets/9999", headers=alice_headers)).status_code == 404
