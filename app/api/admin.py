"""Адмін-панель. Усі маршрути закриті залежністю require_roles(ADMIN) на рівні роутера."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import STATS_KEY, cache
from app.core.config import settings
from app.core.deps import invalidate_user, require_roles
from app.db.database import get_session
from app.models import Appointment, AppointmentStatus, Pet, Role, User
from app.schemas import AdminStats, RoleUpdate, UserRead

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.get("/users", response_model=list[UserRead])
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не можна змінити власну роль")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено")
    user.role = data.role
    await session.commit()
    await invalidate_user(user.id)  # нова роль діє з наступного ж запиту
    return user


@router.get("/stats", response_model=AdminStats)
async def stats(response: Response, session: AsyncSession = Depends(get_session)):
    # ЛР №7: агрегатна статистика кешується на короткий час (CACHE_STATS_TTL, 10 с) без інвалідації —
    # для панелі адміністратора відставання на кілька секунд прийнятне
    cached = await cache.get(STATS_KEY)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    # Було 4 окремі запити (4 звернення до БД) — тепер один запит із чотирма підзапитами
    row = (
        await session.execute(
            select(
                select(func.count()).select_from(User).scalar_subquery().label("users"),
                select(func.count()).select_from(Pet).scalar_subquery().label("pets"),
                select(func.count()).select_from(Appointment).scalar_subquery().label("appointments"),
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.status == AppointmentStatus.SCHEDULED)
                .scalar_subquery()
                .label("scheduled_appointments"),
            )
        )
    ).one()
    payload = AdminStats(**row._mapping).model_dump()
    await cache.set(STATS_KEY, payload, settings.cache_stats_ttl)
    if cache.enabled:
        response.headers["X-Cache"] = "MISS"
    return payload
