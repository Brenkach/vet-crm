"""Адмін-панель. Усі маршрути закриті залежністю require_roles(ADMIN) на рівні роутера."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.db.database import get_session
from app.models import Appointment, AppointmentStatus, Pet, Role, User
from app.schemas import AdminStats, RoleUpdate, UserRead

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.get("/users", response_model=List[UserRead])
async def list_users(session: AsyncSession = Depends(get_session)):
    return (await session.scalars(select(User).order_by(User.id))).all()


@router.patch("/users/{user_id}/role", response_model=UserRead)
async def change_role(
    user_id: int,
    data: RoleUpdate,
    current: User = Depends(require_roles(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    if user_id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не можна змінити власну роль",
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено")
    user.role = data.role
    await session.commit()
    return user


@router.get("/stats", response_model=AdminStats)
async def stats(session: AsyncSession = Depends(get_session)):
    return AdminStats(
        users=await session.scalar(select(func.count(User.id))),
        pets=await session.scalar(select(func.count(Pet.id))),
        appointments=await session.scalar(select(func.count(Appointment.id))),
        scheduled_appointments=await session.scalar(
            select(func.count(Appointment.id)).where(Appointment.status == AppointmentStatus.SCHEDULED)
        ),
    )
