"""Створення адміністратора зі змінних ADMIN_EMAIL / ADMIN_PASSWORD при старті."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.models import Role, User

logger = logging.getLogger("vet_crm.bootstrap")


async def ensure_admin(session_factory: async_sessionmaker, email: str, password: str) -> bool:
    """Створює адміна, якщо користувача з таким email ще немає. Повертає True, якщо створено."""
    async with session_factory() as session:
        if await session.scalar(select(User).where(User.email == email.lower())):
            return False
        session.add(
            User(
                email=email.lower(),
                full_name="Administrator",
                hashed_password=hash_password(password),
                role=Role.ADMIN,
            )
        )
        await session.commit()
    logger.info("Створено адміністратора %s", email)
    return True
