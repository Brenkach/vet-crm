"""Створює .env.sandbox, .env.production і .env (для Docker) із шаблонів *.example.

    python scripts/init_env.py

Для кожного середовища генерується власний SECRET_KEY, тож токени sandbox
не підходять до production. Для Docker також генеруються паролі БД і адміністратора.
Наявні файли не перезаписуються.
"""

import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fill(template: str, key: str, value: str) -> str:
    return re.sub(rf"^{key}=$", f"{key}={value}", template, count=1, flags=re.MULTILINE)


def main() -> None:
    for env in ("sandbox", "production"):
        target = ROOT / f".env.{env}"
        example = ROOT / f".env.{env}.example"
        if target.exists():
            print(f"{target.name} вже існує — пропускаю")
            continue
        if not example.exists():
            print(f"Не знайдено {example.name}")
            continue
        text = fill(example.read_text(encoding="utf-8"), "SECRET_KEY", secrets.token_urlsafe(48))
        if env == "sandbox":
            seed_password = secrets.token_urlsafe(9)
            text = fill(text, "SEED_USER_PASSWORD", seed_password)
            print(f"Пароль демо-користувачів sandbox: {seed_password}")
        target.write_text(text, encoding="utf-8")
        print(f"Створено {target.name}")
    init_docker_env()


def init_docker_env() -> None:
    target = ROOT / ".env"
    example = ROOT / ".env.docker.example"
    if target.exists():
        print(".env вже існує — пропускаю")
        return
    if not example.exists():
        print(f"Не знайдено {example.name}")
        return
    admin_password = secrets.token_urlsafe(9)
    text = example.read_text(encoding="utf-8")
    text = fill(text, "SECRET_KEY", secrets.token_urlsafe(48))
    # token_urlsafe містить лише літери, цифри, "-" і "_" — безпечно для рядка підключення до БД
    text = fill(text, "POSTGRES_PASSWORD", secrets.token_urlsafe(24))
    text = fill(text, "ADMIN_PASSWORD", admin_password)
    target.write_text(text, encoding="utf-8")
    print(f"Створено .env для Docker. Пароль адміністратора (admin@example.com): {admin_password}")


if __name__ == "__main__":
    main()
