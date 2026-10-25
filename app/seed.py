"""Демо-дані для тестового середовища.

    python -m app.seed

Працює ТІЛЬКИ в sandbox: у production скрипт відмовиться запускатися,
тож тестові дані не потраплять у робочу базу.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import models  # noqa: F401
from app.core.config import Environment, Settings, settings
from app.core.security import hash_password
from app.models import Appointment, Pet, Role, User

DEMO_CLIENTS = [
    ("ivan@sandbox.example.com", "Іван Петренко", [("Рекс", "собака", "вівчарка"), ("Мурка", "кішка", None)]),
    ("olena@sandbox.example.com", "Олена Шевчук", [("Бублик", "кролик", None)]),
]


def check_can_seed(cfg: Settings) -> str:
    if cfg.app_env != Environment.SANDBOX:
        raise SystemExit(f"Демо-дані можна завантажувати лише в sandbox (зараз APP_ENV={cfg.app_env.value})")
    if not cfg.seed_user_password:
        raise SystemExit("Задайте SEED_USER_PASSWORD у .env.sandbox")
    return cfg.seed_user_password


async def seed(session_factory: async_sessionmaker, password: str) -> int:
    """Додає демо-клієнтів, тварин і записи. Повторний запуск нічого не дублює. Повертає кількість нових клієнтів."""
    created = 0
    soon = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    async with session_factory() as session:
        for email, name, pets in DEMO_CLIENTS:
            if await session.scalar(select(User).where(User.email == email)):
                continue
            user = User(email=email, full_name=name, hashed_password=hash_password(password), role=Role.CLIENT)
            session.add(user)
            await session.flush()
            for i, (pet_name, species, breed) in enumerate(pets, start=1):
                pet = Pet(name=pet_name, species=species, breed=breed, owner_id=user.id)
                session.add(pet)
                await session.flush()
                session.add(Appointment(pet_id=pet.id, scheduled_at=soon + timedelta(days=i), reason="Плановий огляд"))
            created += 1
        await session.commit()
    return created


async def main() -> None:
    password = check_can_seed(settings)
    from app.db.database import Base, SessionLocal, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    created = await seed(SessionLocal, password)
    await engine.dispose()
    print(f"Додано демо-клієнтів: {created}. Логіни: " + ", ".join(e for e, _, _ in DEMO_CLIENTS))


if __name__ == "__main__":
    asyncio.run(main())
