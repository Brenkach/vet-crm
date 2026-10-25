import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  — реєструє моделі в Base.metadata
from app.api.routes import router
from app.core.bootstrap import ensure_admin
from app.core.config import Settings, settings
from app.core.errors import register_error_handlers
from app.db.database import Base, SessionLocal, engine

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger("vet_crm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg: Settings = app.state.settings
    logger.info("Запуск у середовищі %s, БД: %s, debug=%s", cfg.app_env.value, cfg.safe_database_url, cfg.debug)
    # Для лаби таблиці створюються при старті; у реальному проєкті — міграції Alembic
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if cfg.admin_email and cfg.admin_password:
        await ensure_admin(SessionLocal, cfg.admin_email, cfg.admin_password)
    yield
    await engine.dispose()


def create_app(app_settings: Optional[Settings] = None) -> FastAPI:
    cfg = app_settings or settings
    logging.basicConfig(level=cfg.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = FastAPI(
        title=cfg.app_title,
        debug=cfg.debug,
        lifespan=lifespan,
        # У production документація API не публікується
        docs_url="/docs" if cfg.docs_enabled else None,
        redoc_url="/redoc" if cfg.docs_enabled else None,
        openapi_url="/openapi.json" if cfg.docs_enabled else None,
    )
    app.state.settings = cfg
    register_error_handlers(app)
    app.include_router(router)

    # Веб-інтерфейс: статичні сторінки, які працюють через те саме REST API
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/ui/")

    return app


app = create_app()
