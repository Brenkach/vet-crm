"""Створення адміністратора з консолі (публічна реєстрація адмінів закрита).

Використання:
    python -m app.create_admin --email admin@example.com --name "Admin"
"""

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app import models  # noqa: F401
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import Base, SessionLocal, engine
from app.models import Role, User


async def create_admin(email: str, full_name: str, password: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email.lower()))
        if user:
            user.role = Role.ADMIN
            print(f"Користувача {email} підвищено до адміністратора")
        else:
            session.add(
                User(email=email.lower(), full_name=full_name, hashed_password=hash_password(password), role=Role.ADMIN)
            )
            print(f"Адміністратора {email} створено")
        await session.commit()
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Створити адміністратора")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    print(f"Середовище: {settings.app_env.value}, БД: {settings.safe_database_url}")
    password = getpass.getpass("Пароль (мін. 8 символів): ")
    if len(password) < 8:
        raise SystemExit("Пароль занадто короткий")
    asyncio.run(create_admin(args.email, args.name, password))


if __name__ == "__main__":
    main()
