from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  — реєструє моделі в Base.metadata
from app.api.routes import router
from app.core.config import settings
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Для лаби таблиці створюються при старті; у реальному проєкті — міграції Alembic
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title=settings.app_title, lifespan=lifespan)
app.include_router(router)
