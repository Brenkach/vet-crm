"""Аналіз планів виконання SQL-запитів (EXPLAIN ANALYZE) до і після оптимізацій ЛР №7.

    docker compose -p vet-crm-explain run --rm -e APP_ENV=sandbox app python -m app.explain > docs/explain-analyze.md

Що робить скрипт (лише PostgreSQL, лише не в production):
1. відкриває ОДНУ транзакцію;
2. генерує реалістичний обсяг даних (за замовчуванням 2000 клієнтів, 8000 тварин, 200 000 записів,
   з них ~5% запланованих) і оновлює статистику планувальника (ANALYZE);
3. знімає плани ключових запитів у стані «ДО» (без індексу ЛР №7) і «ПІСЛЯ»;
4. робить ROLLBACK — у базі не залишається ні даних, ні змін.
Результат друкується в stdout у форматі Markdown.
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import Environment, settings

INDEX_SQL = "CREATE INDEX ix_appointments_scheduled ON appointments (scheduled_at) WHERE status = 'scheduled'"
REJECTED_INDEX_SQL = "CREATE INDEX ix_tmp_pet_id_scheduled_at ON appointments (pet_id, scheduled_at)"

GENERATE = [
    """INSERT INTO users (email, full_name, hashed_password, role, is_active)
       SELECT 'explain-' || g || '@example.com', 'Explain ' || g, 'x', 'client', true
       FROM generate_series(1, :users) AS g""",
    """INSERT INTO pets (name, species, owner_id)
       SELECT 'Pet ' || g, 'кіт', u.id
       FROM users u CROSS JOIN generate_series(1, :pets_per_user) AS g
       WHERE u.email LIKE 'explain-%'""",
    # ~5% запланованих, ~3% скасованих, решта — завершені (історія за рік)
    """INSERT INTO appointments (pet_id, scheduled_at, reason, status)
       SELECT p.id,
              now() - interval '400 days' + ((p.id * 37 + g * 101) % 430) * interval '1 day',
              'Огляд',
              CASE WHEN (p.id * 31 + g * 17) % 100 < 5 THEN 'scheduled'
                   WHEN (p.id * 31 + g * 17) % 100 < 8 THEN 'cancelled'
                   ELSE 'completed' END
       FROM pets p CROSS JOIN generate_series(1, :appts_per_pet) AS g
       WHERE p.name LIKE 'Pet %' AND p.owner_id IN (SELECT id FROM users WHERE email LIKE 'explain-%')""",
]

STATS_SCHEDULED = "SELECT count(*) FROM appointments WHERE status = 'scheduled'"
STATS_COMBINED = """SELECT (SELECT count(*) FROM users) AS users,
       (SELECT count(*) FROM pets) AS pets,
       (SELECT count(*) FROM appointments) AS appointments,
       (SELECT count(*) FROM appointments WHERE status = 'scheduled') AS scheduled_appointments"""
CLIENT_APPOINTMENTS = """SELECT appointments.* FROM appointments
       JOIN pets ON pets.id = appointments.pet_id
       WHERE pets.owner_id = :owner ORDER BY appointments.scheduled_at"""
CLIENT_PETS = "SELECT pets.* FROM pets WHERE pets.owner_id = :owner ORDER BY pets.id"
# Додатковий запит, який генерувало lazy="selectin" для кожного GET /pets (до ЛР №7)
SELECTIN_APPOINTMENTS = """SELECT appointments.* FROM appointments
       WHERE appointments.pet_id IN (SELECT id FROM pets WHERE owner_id = :owner)"""


async def explain(conn: AsyncConnection, sql: str, params: dict, repeats: int = 3) -> Tuple[str, float]:
    """Повертає план останнього прогону і найменший час виконання з кількох (перший прогрів кеш)."""
    best, plan = float("inf"), ""
    for _ in range(repeats):
        rows = (await conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params)).scalars().all()
        plan = "\n".join(rows)
        match = re.search(r"Execution Time: ([\d.]+) ms", plan)
        if match:
            best = min(best, float(match.group(1)))
    return plan, best


def block(title: str, sql: str, plan: str) -> List[str]:
    return [f"**{title}**", "", "```sql", " ".join(sql.split()), "```", "", "```", plan, "```", ""]


async def run(args) -> List[str]:
    engine = create_async_engine(settings.database_url)
    out: List[str] = []
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in GENERATE:
                await conn.execute(
                    text(sql),
                    {
                        "users": args.users,
                        "pets_per_user": args.pets_per_user,
                        "appts_per_pet": args.appointments_per_pet,
                    },
                )
            for table in ("users", "pets", "appointments"):
                await conn.execute(text(f"ANALYZE {table}"))
            counts = (await conn.execute(text(STATS_COMBINED))).one()
            owner = await conn.scalar(text("SELECT id FROM users WHERE email = 'explain-1000@example.com'"))
            version = await conn.scalar(text("SHOW server_version"))
            params = {"owner": owner}

            # ---------- ДО: без індексу ЛР №7 ----------
            await conn.execute(text("DROP INDEX IF EXISTS ix_appointments_scheduled"))
            before_count, t_before_count = await explain(conn, STATS_SCHEDULED, params)
            before_combined, t_before_combined = await explain(conn, STATS_COMBINED, params)

            # ---------- ПІСЛЯ ----------
            await conn.execute(text(INDEX_SQL))
            await conn.execute(text("ANALYZE appointments"))
            after_count, t_after_count = await explain(conn, STATS_SCHEDULED, params)
            after_combined, t_after_combined = await explain(conn, STATS_COMBINED, params)

            # ---------- Запити клієнта ----------
            client_appts, t_client_appts = await explain(conn, CLIENT_APPOINTMENTS, params)
            client_pets, t_client_pets = await explain(conn, CLIENT_PETS, params)
            selectin, t_selectin = await explain(conn, SELECTIN_APPOINTMENTS, params)
            await conn.execute(text(REJECTED_INDEX_SQL))
            await conn.execute(text("ANALYZE appointments"))
            client_appts_composite, t_client_appts_composite = await explain(conn, CLIENT_APPOINTMENTS, params)
        finally:
            await trans.rollback()  # жодних слідів у базі
    await engine.dispose()

    def ratio(a: float, b: float) -> str:
        return f"у {a / b:.1f} раза швидше" if b and a > b else "без суттєвої різниці"

    out += [
        "# EXPLAIN ANALYZE: плани запитів до і після оптимізації (ЛР №7)",
        "",
        f"Згенеровано: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, PostgreSQL {version}, "
        f"скрипт `python -m app.explain`.",
        "",
        f"Тестові дані (у транзакції, яку скасовано після аналізу): {counts.users} користувачів, "
        f"{counts.pets} тварин, {counts.appointments} записів на прийом, з них {counts.scheduled_appointments} "
        "запланованих. Для кожного запиту наведено найкращий час із трьох прогонів.",
        "",
        "## Підсумок",
        "",
        "| Запит | ДО, мс | ПІСЛЯ, мс | Результат |",
        "|---|---:|---:|---|",
        f"| Кількість запланованих прийомів (статистика адміна) | {t_before_count:.2f} | {t_after_count:.2f} | "
        f"{ratio(t_before_count, t_after_count)} |",
        "| Уся статистика адміна (один запит із чотирма підзапитами) | "
        f"{t_before_combined:.2f} | {t_after_combined:.2f} | "
        f"{ratio(t_before_combined, t_after_combined)} |",
        f"| `GET /pets` клієнта | {t_client_pets + t_selectin:.2f} (2 запити) | {t_client_pets:.2f} (1 запит) | "
        "зайвий запит прибрано |",
        f"| `GET /appointments` клієнта | {t_client_appts:.2f} | {t_client_appts:.2f} | "
        "вже оптимальний, змін не потребує |",
        f"| `GET /appointments` клієнта зі складеним індексом (pet_id, scheduled_at) | {t_client_appts:.2f} | "
        f"{t_client_appts_composite:.2f} | {ratio(t_client_appts, t_client_appts_composite)} — індекс відхилено |",
        "",
        "## 1. Кількість запланованих прийомів: частковий індекс",
        "",
        "Без індексу PostgreSQL переглядає всю таблицю (`Seq Scan`) і відкидає ~95% рядків фільтром. "
        "Частковий індекс `ix_appointments_scheduled` містить лише заплановані прийоми, тож запит читає "
        "тільки потрібні рядки (`Bitmap Index Scan`).",
        "",
    ]
    out += block("ДО (без індексу)", STATS_SCHEDULED, before_count)
    out += block("ПІСЛЯ (з індексом ix_appointments_scheduled)", STATS_SCHEDULED, after_count)
    out += ["## 2. Статистика адміністратора одним запитом", ""]
    out += block("ДО (без індексу)", STATS_COMBINED, before_combined)
    out += block("ПІСЛЯ (з індексом)", STATS_COMBINED, after_combined)
    out += [
        '## 3. `GET /pets`: зайвий запит, який генерувало `lazy="selectin"`',
        "",
        "До ЛР №7 кожне завантаження тварин автоматично тягнуло всі їхні записи на прийом, хоча відповідь "
        "API їх не містить. Нижче — цей зайвий запит. Після оптимізації він не виконується взагалі.",
        "",
    ]
    out += block("Запит, що виконується (і до, і після)", CLIENT_PETS, client_pets)
    out += block("Зайвий запит, що виконувався лише ДО оптимізації", SELECTIN_APPOINTMENTS, selectin)
    out += [
        "## 4. `GET /appointments`: перевірений, але відхилений індекс",
        "",
        "Запит уже використовує наявні індекси `ix_pets_owner_id` і `ix_appointments_pet_id` (`Nested Loop` з "
        "`Index Scan`). Складений індекс `(pet_id, scheduled_at)` перевірено, але він не дає виграшу, а кожен "
        "індекс уповільнює вставку, тому його не додано.",
        "",
    ]
    out += block("Поточний план", CLIENT_APPOINTMENTS, client_appts)
    out += block("Зі складеним індексом (pet_id, scheduled_at)", CLIENT_APPOINTMENTS, client_appts_composite)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="EXPLAIN ANALYZE ключових запитів")
    parser.add_argument("--users", type=int, default=2000)
    parser.add_argument("--pets-per-user", type=int, default=4)
    parser.add_argument("--appointments-per-pet", type=int, default=25)
    args = parser.parse_args()
    if settings.app_env == Environment.PRODUCTION:
        sys.exit("Аналіз тимчасово змінює індекси й блокує таблиці — запускайте його лише в sandbox")
    if not settings.database_url.startswith("postgresql"):
        sys.exit("EXPLAIN ANALYZE у цьому форматі підтримується лише для PostgreSQL")
    print("\n".join(asyncio.run(run(args))))


if __name__ == "__main__":
    main()
