"""Базова бізнес-логіка MVP: тварини та записи на прийом."""

from datetime import datetime, timedelta, timezone


async def test_full_client_flow(client, bob_headers, bob_pet):
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    created = await client.post(
        "/appointments",
        json={"pet_id": bob_pet["id"], "scheduled_at": when, "reason": "Огляд"},
        headers=bob_headers,
    )
    assert created.status_code == 201
    appt_id = created.json()["id"]

    listed = await client.get("/appointments", headers=bob_headers)
    assert [a["id"] for a in listed.json()] == [appt_id]

    cancelled = await client.post(f"/appointments/{appt_id}/cancel", headers=bob_headers)
    assert cancelled.json()["status"] == "cancelled"
    # повторне скасування — конфлікт
    assert (await client.post(f"/appointments/{appt_id}/cancel", headers=bob_headers)).status_code == 409


async def test_cannot_book_in_the_past(client, bob_headers, bob_pet):
    when = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp = await client.post(
        "/appointments",
        json={"pet_id": bob_pet["id"], "scheduled_at": when, "reason": "Огляд"},
        headers=bob_headers,
    )
    assert resp.status_code == 400


async def test_admin_stats(client, admin_headers, bob_appointment):
    stats = (await client.get("/admin/stats", headers=admin_headers)).json()
    assert stats["pets"] == 1 and stats["appointments"] == 1 and stats["scheduled_appointments"] == 1
