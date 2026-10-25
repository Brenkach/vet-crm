"""Створює .env.sandbox та .env.production із шаблонів *.example.

    python scripts/init_env.py

Для кожного середовища генерується власний SECRET_KEY, тож токени sandbox
не підходять до production. Наявні файли не перезаписуються.
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


if __name__ == "__main__":
    main()
