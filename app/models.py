import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Role(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _enum_column(enum_cls):
    # Зберігаємо значення ("admin"), а не імена ("ADMIN"); без нативного ENUM — працює і в SQLite, і в Postgres
    return SAEnum(enum_cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum_column(Role), default=Role.CLIENT)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pets: Mapped[list["Pet"]] = relationship(back_populates="owner")


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    species: Mapped[str] = mapped_column(String(50))
    breed: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    owner: Mapped[User] = relationship(back_populates="pets")
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="pet", cascade="all, delete-orphan", lazy="selectin"
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum_column(AppointmentStatus), default=AppointmentStatus.SCHEDULED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # selectin: власник тварини потрібен для перевірки прав, а lazy-load в async заборонений
    pet: Mapped[Pet] = relationship(back_populates="appointments", lazy="selectin")
