from fastapi import APIRouter

from app.api import admin, appointments, auth, home, pets, users

router = APIRouter()
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(home.router)
router.include_router(pets.router)
router.include_router(appointments.router)
router.include_router(admin.router)
