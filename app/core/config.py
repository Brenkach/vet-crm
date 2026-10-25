"""Конфігурація застосунку.

Усі налаштування читаються зі змінних оточення та файлу `.env.<APP_ENV>` у корені проєкту:
    APP_ENV=sandbox    -> .env.sandbox     (тестове середовище, за замовчуванням)
    APP_ENV=production -> .env.production  (робоче середовище)
    APP_ENV=test       -> лише змінні оточення (pytest, CI)

Секретів і адреси БД у коді немає: без них застосунок не запуститься.
Змінні оточення мають пріоритет над файлом — так налаштування передають хостинг і CI.
"""

import enum
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parents[2]


class Environment(str, enum.Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file_encoding="utf-8")

    app_env: Environment = Environment.SANDBOX
    app_title: str = "Vet CRM"
    debug: bool = False  # безпечне значення за замовчуванням
    docs_enabled: bool = False  # Swagger (/docs) вмикається явно
    log_level: str = "INFO"

    # Обов'язкові — значень за замовчуванням немає
    database_url: str
    secret_key: str = Field(min_length=32)

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)

    # Необов'язкові: автостворення адміна при старті (зручно для хостингу без консолі)
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    # Пароль демо-користувачів для `python -m app.seed` (тільки sandbox)
    seed_user_password: Optional[str] = None

    @field_validator("database_url")
    @classmethod
    def use_async_driver(cls, value: str) -> str:
        # Хостинги (Render, Railway) видають postgres://... — для async SQLAlchemy потрібен asyncpg
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @field_validator("admin_email", "admin_password", "seed_user_password", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return value or None

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        if self.app_env == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("DEBUG=true заборонено в production")
            if "sandbox" in self.database_url or ":memory:" in self.database_url:
                raise ValueError("Production не може використовувати базу даних sandbox або тестову")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def safe_database_url(self) -> str:
        """Адреса БД для логів — без пароля."""
        return make_url(self.database_url).render_as_string(hide_password=True)


def env_file_for(environment: Environment, base_dir: Path = BASE_DIR) -> Optional[Path]:
    path = base_dir / f".env.{environment.value}"
    return path if path.is_file() else None


def load_settings(env: Optional[str] = None, base_dir: Path = BASE_DIR) -> Settings:
    name = env or os.getenv("APP_ENV", Environment.SANDBOX.value)
    try:
        environment = Environment(name)
    except ValueError:
        allowed = ", ".join(e.value for e in Environment)
        raise RuntimeError(f"Невідоме APP_ENV={name!r}. Допустимі значення: {allowed}") from None
    return Settings(_env_file=env_file_for(environment, base_dir), app_env=environment)


@lru_cache
def get_settings() -> Settings:
    return load_settings()


settings = get_settings()
