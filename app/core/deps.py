"""Залежності FastAPI: поточний користувач, перевірка ролей і власника ресурсу."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache, user_key
from app.core.config import settings
from app.core.security import decode_access_token
from app.db.database import get_session
from app.models import Role, User

# auto_error=True -> без токена FastAPI сам повертає 401
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не вдалося підтвердити облікові дані",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_error
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise credentials_error

    # ЛР №7: користувач потрібен на КОЖНОМУ запиті, тож профіль кешується в Redis.
    # Роль, як і раніше, береться не з токена: при зміні ролі чи профілю ключ видаляється
    # (див. invalidate_user), тож зміна діє одразу.
    cached = await cache.get(user_key(user_id))
    if cached is not None:
        user = User(**{**cached, "role": Role(cached["role"])})
    else:
        user = await session.get(User, user_id)
        if user is not None:
            await cache.set(user_key(user_id), user_to_cache(user), settings.cache_user_ttl)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def user_to_cache(user: User) -> dict:
    # Хеш пароля в кеш не потрапляє
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
    }


async def invalidate_user(user_id: int) -> None:
    await cache.delete(user_key(user_id))


def require_roles(*roles: Role) -> Callable:
    """Вертикальне розмежування: доступ лише для перелічених ролей, інакше 403."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")
        return user

    return checker


def ensure_owner_or_admin(user: User, owner_id: int) -> None:
    """Горизонтальне розмежування (захист від IDOR): чужі ресурси — лише для адміна."""
    if user.role != Role.ADMIN and user.id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ до чужого ресурсу заборонено")
