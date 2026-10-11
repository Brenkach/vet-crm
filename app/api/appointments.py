from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pets import get_pet_or_404
from app.core.deps import ensure_owner_or_admin, get_current_user, require_roles
from app.db.database import get_session
from app.models import Appointment, AppointmentStatus, Pet, Role, User
from app.schemas import AppointmentCreate, AppointmentRead, AppointmentStatusUpdate

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def _get_appointment_or_404(session: AsyncSession, appointment_id: int) -> Appointment:
    appointment = await session.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запис не знайдено")
    return appointment


@router.get("", response_model=List[AppointmentRead])
async def list_appointments(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = select(Appointment).order_by(Appointment.scheduled_at)
    if user.role != Role.ADMIN:
        stmt = stmt.join(Pet).where(Pet.owner_id == user.id)
    return (await session.scalars(stmt)).all()


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pet = await get_pet_or_404(session, data.pet_id)
    ensure_owner_or_admin(user, pet.owner_id)  # не можна записати на прийом чужу тварину

    scheduled_at = _as_utc(data.scheduled_at)
    if scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не можна записатися на минулий час",
        )

    appointment = Appointment(pet_id=pet.id, scheduled_at=scheduled_at, reason=data.reason)
    session.add(appointment)
    await session.commit()
    await session.refresh(appointment)
    return appointment


@router.get("/{appointment_id}", response_model=AppointmentRead)
async def read_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    appointment = await _get_appointment_or_404(session, appointment_id)
    ensure_owner_or_admin(user, appointment.pet.owner_id)
    return appointment


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead)
async def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    appointment = await _get_appointment_or_404(session, appointment_id)
    ensure_owner_or_admin(user, appointment.pet.owner_id)
    if appointment.status != AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Скасувати можна лише запланований запис",
        )
    appointment.status = AppointmentStatus.CANCELLED
    await session.commit()
    return appointment


@router.patch("/{appointment_id}/status", response_model=AppointmentRead)
async def set_appointment_status(
    appointment_id: int,
    data: AppointmentStatusUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    appointment = await _get_appointment_or_404(session, appointment_id)
    appointment.status = data.status
    await session.commit()
    return appointment
