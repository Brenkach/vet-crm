import socket

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])

# Ідентифікатор екземпляра: у Docker hostname контейнера — це його короткий ID
INSTANCE_ID = socket.gethostname()


@router.get("/health")
async def health(request: Request):
    """Стан сервісу, назва середовища і ідентифікатор репліки, яка обробила запит."""
    return {"status": "ok", "environment": request.app.state.settings.app_env.value, "instance": INSTANCE_ID}
