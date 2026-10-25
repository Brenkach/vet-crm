"""Обробка непередбачених помилок.

У sandbox (DEBUG=true) Starlette показує розробнику повний стектрейс.
У production (DEBUG=false) користувач бачить лише нейтральне повідомлення з кодом помилки,
а сам стектрейс записується в лог сервера — за кодом його легко знайти.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("vet_crm.errors")

GENERIC_MESSAGE = "Внутрішня помилка сервера. Спробуйте пізніше."

ERROR_PAGE = """<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Помилка сервера — ВетКлініка</title>
  <link rel="stylesheet" href="/ui/style.css">
</head>
<body>
  <main class="error-page">
    <h1>Щось пішло не так</h1>
    <p>На сервері сталася помилка. Ми вже знаємо про неї — спробуйте оновити сторінку пізніше.</p>
    <p class="muted">Код помилки: <b>__ERROR_ID__</b></p>
    <p><a class="btn" href="/">На головну</a></p>
  </main>
</body>
</html>
"""


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:12]
        logger.error("Необроблена помилка %s: %s %s", error_id, request.method, request.url.path, exc_info=exc)
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(ERROR_PAGE.replace("__ERROR_ID__", error_id), status_code=500)
        return JSONResponse({"detail": GENERIC_MESSAGE, "error_id": error_id}, status_code=500)
