from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_owner_or_admin, get_current_user
from app.db.database import get_session
from app.models import Pet, Role, User
from app.schemas import PetCreate, PetRead, PetUpdate

router = APIRouter(prefix="/pets", tags=["pets"])


async def get_pet_or_404(session: AsyncSession, pet_id: int) -> Pet:
    pet = await session.get(Pet, pet_id)
    if pet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тварину не знайдено")
    return pet


@router.get("", response_model=List[PetRead])
async def list_pets(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stmt = select(Pet).order_by(Pet.id)
    if user.role != Role.ADMIN:
        stmt = stmt.where(Pet.owner_id == user.id)
    return (await session.scalars(stmt)).all()


@router.post("", response_model=PetRead, status_code=status.HTTP_201_CREATED)
async def create_pet(
    data: PetCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # owner_id береться з токена, а не з тіла запиту
    pet = Pet(**data.model_dump(), owner_id=user.id)
    session.add(pet)
    await session.commit()
    await session.refresh(pet)
    return pet


@router.get("/{pet_id}", response_model=PetRead)
async def read_pet(
    pet_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pet = await get_pet_or_404(session, pet_id)
    ensure_owner_or_admin(user, pet.owner_id)
    return pet


@router.patch("/{pet_id}", response_model=PetRead)
async def update_pet(
    pet_id: int,
    data: PetUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pet = await get_pet_or_404(session, pet_id)
    ensure_owner_or_admin(user, pet.owner_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pet, field, value)
    await session.commit()
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pet(
    pet_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    pet = await get_pet_or_404(session, pet_id)
    ensure_owner_or_admin(user, pet.owner_id)
    await session.delete(pet)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
