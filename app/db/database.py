from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def engine_options(database_url: str) -> dict:
    options = {"pool_pre_ping": True}
    if make_url(database_url).get_backend_name() == "postgresql":
        # Розмір пулу задається явно: 3 репліки × (10 + 10) = 60 з'єднань < max_connections=100 PostgreSQL
        options.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow)
    return options


def enable_sqlite_foreign_keys(sync_engine: Engine) -> None:
    """SQLite за замовчуванням ігнорує ON DELETE CASCADE — вмикаємо, як у PostgreSQL."""

    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_async_engine(settings.database_url, **engine_options(settings.database_url))
if engine.dialect.name == "sqlite":
    enable_sqlite_foreign_keys(engine.sync_engine)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as session:
        yield session
