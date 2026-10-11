"""Залежності FastAPI: поточний користувач, перевірка ролей і власника ресурсу."""

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Роль беремо з БД, а не з токена: зміна ролі адміном діє одразу
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ до чужого ресурсу заборонено",
        )
