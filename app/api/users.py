from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_owner_or_admin, get_current_user
from app.core.security import hash_password
from app.db.database import get_session
from app.models import User
from app.schemas import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено")
    return user


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(get_current_user)):
    return user


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    target = await _get_user_or_404(session, user_id)
    ensure_owner_or_admin(current, target.id)
    return target


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    data: UserUpdate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    target = await _get_user_or_404(session, user_id)
    ensure_owner_or_admin(current, target.id)

    if data.full_name is not None:
        target.full_name = data.full_name
    if data.password is not None:
        target.hashed_password = hash_password(data.password)
    await session.commit()
    return target
