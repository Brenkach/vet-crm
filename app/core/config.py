from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_title: str = "Vet CRM"
    # Для Postgres з docker-compose: postgresql+asyncpg://user:pass@localhost:5432/vet_crm
    database_url: str = "sqlite+aiosqlite:///./vet_crm.db"

    # У продакшені обов'язково задати через змінну оточення SECRET_KEY
    secret_key: str = "dev-only-secret-key-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
