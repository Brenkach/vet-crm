from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request):
    """Перевірка роботи сервісу (використовує хостинг) і назва середовища для інтерфейсу."""
    return {"status": "ok", "environment": request.app.state.settings.app_env.value}
