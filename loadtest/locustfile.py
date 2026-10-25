"""Сценарії навантажувального тестування Vet CRM (Locust).

Рекомендований запуск — через обгортку з моніторингом ресурсів і звітом:
    python loadtest/run.py baseline
Напряму (з веб-інтерфейсом Locust на http://localhost:8089):
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000

Суміш віртуальних користувачів відтворює реальну аудиторію клініки:
    ClientUser    (вага 6) — клієнт: реєстрація, вхід, кабінет, тварини, записи на прийом
    AnonymousUser (вага 2) — відвідувач: головна, сторінка входу, перевірка стану сервісу
    AdminUser     (вага 1) — адміністратор: статистика, користувачі, усі записи
                             (лише якщо задано LOADTEST_ADMIN_EMAIL і LOADTEST_ADMIN_PASSWORD)
"""

import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from locust import HttpUser, LoadTestShape, between, task
from locust.exception import StopUser

# Пароль віртуальних клієнтів генерується на кожен запуск — у коді його немає
USER_PASSWORD = os.getenv("LOADTEST_USER_PASSWORD") or uuid.uuid4().hex
ADMIN_EMAIL = os.getenv("LOADTEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("LOADTEST_ADMIN_PASSWORD")

SPECIES = ["собака", "кіт", "кролик", "папуга", "хом'як"]


def future_time() -> str:
    moment = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(1, 10))
    return moment.replace(minute=0, second=0, microsecond=0).isoformat()


class ClientUser(HttpUser):
    """Клієнт клініки — основна аудиторія."""

    weight = 6
    wait_time = between(1, 3)  # «час на роздуми» між діями

    def on_start(self):
        self.headers = {}
        self.pet_ids = []
        self.scheduled_ids = []
        # До 3 спроб: під навантаженням реєстрація може впасти з 500 — це фіксується як помилка в статистиці
        for _ in range(3):
            if self.sign_up():
                break
        else:
            # Без входу користувач лише генерував би каскад 401 і спотворив Error Rate — зупиняємо його
            raise StopUser()
        self.add_pet()

    def sign_up(self) -> bool:
        email = f"load-{uuid.uuid4().hex[:12]}@sandbox.example.com"
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "full_name": "Навантажувальний тест", "password": USER_PASSWORD},
            name="POST /auth/register",
        )
        if resp.status_code != 201:
            return False
        resp = self.client.post(
            "/auth/login", data={"username": email, "password": USER_PASSWORD}, name="POST /auth/login"
        )
        if resp.status_code != 200:
            return False
        self.headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        return True

    @task(4)
    def home(self):
        self.client.get("/home", headers=self.headers, name="GET /home")

    @task(4)
    def list_pets(self):
        resp = self.client.get("/pets", headers=self.headers, name="GET /pets")
        if resp.status_code == 200:
            self.pet_ids = [pet["id"] for pet in resp.json()]

    @task(3)
    def list_appointments(self):
        resp = self.client.get("/appointments", headers=self.headers, name="GET /appointments")
        if resp.status_code == 200:
            self.scheduled_ids = [a["id"] for a in resp.json() if a["status"] == "scheduled"]

    @task(2)
    def profile(self):
        self.client.get("/users/me", headers=self.headers, name="GET /users/me")

    @task(1)
    def open_cabinet_page(self):
        self.client.get("/ui/client.html", name="GET /ui/client.html")

    @task(1)
    def add_pet(self):
        resp = self.client.post(
            "/pets",
            json={"name": f"Тест-{random.randint(1, 9999)}", "species": random.choice(SPECIES)},
            headers=self.headers,
            name="POST /pets",
        )
        if resp.status_code == 201:
            self.pet_ids.append(resp.json()["id"])

    @task(1)
    def book_appointment(self):
        if not self.pet_ids:
            return
        resp = self.client.post(
            "/appointments",
            json={"pet_id": random.choice(self.pet_ids), "scheduled_at": future_time(), "reason": "Плановий огляд"},
            headers=self.headers,
            name="POST /appointments",
        )
        if resp.status_code == 201:
            self.scheduled_ids.append(resp.json()["id"])

    @task(1)
    def cancel_appointment(self):
        if not self.scheduled_ids:
            return
        appointment_id = self.scheduled_ids.pop(random.randrange(len(self.scheduled_ids)))
        self.client.post(
            f"/appointments/{appointment_id}/cancel", headers=self.headers, name="POST /appointments/{id}/cancel"
        )


class AnonymousUser(HttpUser):
    """Відвідувач без облікового запису."""

    weight = 2
    wait_time = between(2, 5)

    @task(3)
    def landing(self):
        # "/" перенаправляє на /ui/ — Locust іде за перенаправленням, як і браузер
        self.client.get("/", name="GET / (→ /ui/)")

    @task(2)
    def login_page(self):
        self.client.get("/ui/login.html", name="GET /ui/login.html")

    @task(1)
    def health(self):
        self.client.get("/health", name="GET /health")


if ADMIN_EMAIL and ADMIN_PASSWORD:

    class AdminUser(HttpUser):
        """Адміністратор клініки."""

        weight = 1
        wait_time = between(2, 4)

        def on_start(self):
            self.headers = {}
            resp = self.client.post(
                "/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, name="POST /auth/login"
            )
            if resp.status_code == 200:
                self.headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        @task(3)
        def stats(self):
            self.client.get("/admin/stats", headers=self.headers, name="GET /admin/stats")

        @task(2)
        def users(self):
            self.client.get("/admin/users", headers=self.headers, name="GET /admin/users")

        @task(2)
        def all_appointments(self):
            self.client.get("/appointments", headers=self.headers, name="GET /appointments")


if os.getenv("LOAD_SHAPE") == "step":

    class StepLoad(LoadTestShape):
        """Ступінчасте навантаження для пошуку точки, де система починає деградувати."""

        stages = [int(n) for n in os.getenv("LOAD_STAGES", "10,25,50,100,150").split(",")]
        stage_seconds = int(os.getenv("LOAD_STAGE_SECONDS", "60"))
        spawn_rate = float(os.getenv("LOAD_SPAWN_RATE", "5"))

        def tick(self):
            stage = int(self.get_run_time() // self.stage_seconds)
            if stage >= len(self.stages):
                return None  # кінець тесту
            return self.stages[stage], self.spawn_rate
