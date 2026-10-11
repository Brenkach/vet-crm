"""Домашні сторінки-заглушки для різних ролей."""

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, require_roles
from app.models import Role, User
from app.schemas import HomePage

router = APIRouter(prefix="/home", tags=["home"])


def _admin_home(user: User) -> HomePage:
    return HomePage(
        title="Панель адміністратора",
        message=f"Вітаємо, {user.full_name}! Тут буде керування клінікою.",
        role=user.role,
        available_sections=["/admin/users", "/admin/stats", "/pets", "/appointments"],
    )


def _client_home(user: User) -> HomePage:
    return HomePage(
        title="Кабінет клієнта",
        message=f"Вітаємо, {user.full_name}! Тут ваші улюбленці та записи до лікаря.",
        role=user.role,
        available_sections=["/users/me", "/pets", "/appointments"],
    )


@router.get("", response_model=HomePage)
async def home(user: User = Depends(get_current_user)):
    """Спільна точка входу: повертає домашню сторінку відповідно до ролі."""
    return _admin_home(user) if user.role == Role.ADMIN else _client_home(user)


@router.get("/admin", response_model=HomePage)
async def admin_home(user: User = Depends(require_roles(Role.ADMIN))):
    return _admin_home(user)


@router.get("/client", response_model=HomePage)
async def client_home(user: User = Depends(require_roles(Role.CLIENT))):
    return _client_home(user)
