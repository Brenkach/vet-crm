"""Обробка помилок 500 і режим відладки в різних середовищах."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app

SECRET = "x" * 40


def build_app(env: Environment, debug: bool, docs: bool = False):
    cfg = Settings(
        _env_file=None,
        app_env=env,
        debug=debug,
        docs_enabled=docs,
        # файл не створюється: lifespan у цих тестах не запускається
        database_url="sqlite+aiosqlite:///./vet_crm_production.db",
        secret_key=SECRET,
    )
    app = create_app(cfg)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("секретна внутрішня деталь: password=hunter2")

    return app


async def request(app, path, accept="application/json"):
    # raise_app_exceptions=False — бачимо відповідь так, як її побачить користувач
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"Accept": accept})


@pytest.fixture
def production_app():
    return build_app(Environment.PRODUCTION, debug=False)


async def test_production_500_json_hides_internals(production_app):
    resp = await request(production_app, "/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Внутрішня помилка сервера. Спробуйте пізніше."
    assert len(body["error_id"]) == 12
    assert "hunter2" not in resp.text and "Traceback" not in resp.text and "RuntimeError" not in resp.text


async def test_production_500_html_page_hides_internals(production_app):
    resp = await request(production_app, "/boom", accept="text/html")
    assert resp.status_code == 500
    assert "text/html" in resp.headers["content-type"]
    assert "Щось пішло не так" in resp.text
    assert "hunter2" not in resp.text and "Traceback" not in resp.text


async def test_production_500_is_logged_with_traceback(production_app, caplog):
    resp = await request(production_app, "/boom")
    error_id = resp.json()["error_id"]
    assert error_id in caplog.text and "hunter2" in caplog.text  # подробиці — лише в лозі сервера


async def test_sandbox_debug_shows_traceback_to_developer():
    resp = await request(build_app(Environment.SANDBOX, debug=True), "/boom", accept="text/html")
    assert resp.status_code == 500
    assert "Traceback" in resp.text or "RuntimeError" in resp.text


async def test_docs_hidden_in_production(production_app):
    assert (await request(production_app, "/docs")).status_code == 404
    assert (await request(production_app, "/openapi.json")).status_code == 404


async def test_docs_available_in_sandbox():
    app = build_app(Environment.SANDBOX, debug=True, docs=True)
    assert (await request(app, "/docs")).status_code == 200


async def test_health_reports_environment(production_app):
    resp = await request(production_app, "/health")
    assert resp.json() == {"status": "ok", "environment": "production"}


async def test_regular_http_errors_unchanged(production_app):
    # 401/403/404 як і раніше повертають зрозуміле повідомлення
    assert (await request(production_app, "/users/me")).status_code == 401
