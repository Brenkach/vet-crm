"""Юніт-тести конфігурації: розділення середовищ і правила безпеки production."""

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings, load_settings

SECRET = "x" * 40


def make(**overrides) -> Settings:
    values = {"database_url": "sqlite+aiosqlite:///./prod.db", "secret_key": SECRET}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def write_env(directory, env, content):
    (directory / f".env.{env}").write_text(content, encoding="utf-8")


# ---------- Читання з .env.<середовище> ----------
def test_sandbox_and_production_read_their_own_files(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("SECRET_KEY")
    write_env(
        tmp_path, "sandbox", f"DATABASE_URL=sqlite+aiosqlite:///./sandbox.db\nSECRET_KEY={'s' * 40}\nDEBUG=true\n"
    )
    write_env(tmp_path, "production", f"DATABASE_URL=sqlite+aiosqlite:///./prod.db\nSECRET_KEY={'p' * 40}\n")

    sandbox = load_settings("sandbox", base_dir=tmp_path)
    production = load_settings("production", base_dir=tmp_path)

    assert sandbox.app_env == Environment.SANDBOX and production.app_env == Environment.PRODUCTION
    assert sandbox.database_url != production.database_url  # ізоляція БД
    assert sandbox.secret_key != production.secret_key
    assert sandbox.debug is True and production.debug is False


def test_environment_variables_override_file(tmp_path, monkeypatch):
    write_env(tmp_path, "production", f"DATABASE_URL=sqlite+aiosqlite:///./prod.db\nSECRET_KEY={'p' * 40}\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/vet")
    cfg = load_settings("production", base_dir=tmp_path)
    assert cfg.database_url == "postgresql+asyncpg://u:p@db.example.com/vet"


def test_unknown_environment_is_rejected():
    with pytest.raises(RuntimeError, match="APP_ENV"):
        load_settings("staging")


# ---------- Жодних захардкоджених секретів ----------
def test_secret_key_has_no_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ValidationError, match="secret_key"):
        load_settings("production", base_dir=tmp_path)


def test_database_url_has_no_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError, match="database_url"):
        load_settings("production", base_dir=tmp_path)


def test_short_secret_key_is_rejected():
    with pytest.raises(ValidationError):
        make(secret_key="too-short")


# ---------- Безпека production ----------
def test_debug_is_off_by_default():
    assert make(app_env=Environment.PRODUCTION).debug is False


def test_debug_forbidden_in_production():
    with pytest.raises(ValidationError, match="DEBUG"):
        make(app_env=Environment.PRODUCTION, debug=True)


def test_debug_allowed_in_sandbox():
    assert make(app_env=Environment.SANDBOX, debug=True).debug is True


def test_production_cannot_use_sandbox_database():
    with pytest.raises(ValidationError, match="sandbox"):
        make(app_env=Environment.PRODUCTION, database_url="sqlite+aiosqlite:///./vet_crm_sandbox.db")


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@host/db", "postgresql://u:p@host/db"],
)
def test_hosting_postgres_url_gets_async_driver(url):
    assert make(database_url=url).database_url == "postgresql+asyncpg://u:p@host/db"


def test_password_hidden_in_logged_url():
    cfg = make(database_url="postgresql+asyncpg://vet:SuperSecret@host/db")
    assert "SuperSecret" not in cfg.safe_database_url


def test_empty_optional_values_become_none():
    assert make(admin_email="", admin_password="").admin_email is None
