from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AppointmentStatus, Role


# ---------- Користувачі / автентифікація ----------
class UserRegister(BaseModel):
    # Поля role тут свідомо немає: при реєстрації не можна обрати роль адміністратора
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=72)  # 72 байти — ліміт bcrypt


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class RoleUpdate(BaseModel):
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HomePage(BaseModel):
    title: str
    message: str
    role: Role
    available_sections: List[str]


# ---------- Тварини ----------
class PetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    species: str = Field(min_length=1, max_length=50)
    breed: Optional[str] = Field(default=None, max_length=100)
    birth_date: Optional[date] = None


class PetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    species: Optional[str] = Field(default=None, min_length=1, max_length=50)
    breed: Optional[str] = Field(default=None, max_length=100)
    birth_date: Optional[date] = None


class PetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    species: str
    breed: Optional[str]
    birth_date: Optional[date]
    owner_id: int


# ---------- Записи на прийом ----------
class AppointmentCreate(BaseModel):
    pet_id: int
    scheduled_at: datetime
    reason: str = Field(min_length=1, max_length=1000)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    scheduled_at: datetime
    reason: str
    status: AppointmentStatus


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus


class AdminStats(BaseModel):
    users: int
    pets: int
    appointments: int
    scheduled_appointments: int
