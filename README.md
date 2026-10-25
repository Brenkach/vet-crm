# Vet CRM

Система для ветеринарної клініки: клієнти реєструються, додають своїх тварин і записуються на прийом, адміністратор керує записами та користувачами.

Стек: FastAPI, SQLAlchemy 2.0 (async), Pydantic Settings, JWT, bcrypt, pytest, GitHub Actions, Render.

![CI](https://github.com/Brenkach/vet-crm/actions/workflows/ci.yml/badge.svg)

## Середовища

Застосунок має два окремі середовища. Яке з них запускається, визначає змінна `APP_ENV`.

| | Sandbox (тестове) | Production (робоче) |
|---|---|---|
| `APP_ENV` | `sandbox` (за замовчуванням) | `production` |
| Файл налаштувань | `.env.sandbox` | `.env.production` або змінні хостингу |
| База даних | `vet_crm_sandbox.db` | `vet_crm_production.db` або PostgreSQL |
| `DEBUG` | `true` — розробник бачить стектрейс | `false` — увімкнути неможливо |
| Документація API `/docs` | доступна | вимкнена |
| Помилка 500 | повний стектрейс | сторінка «Щось пішло не так» з кодом помилки |
| Демо-дані (`app.seed`) | дозволені | заборонені |
| Позначка в інтерфейсі | жовта смуга «Тестове середовище» | немає |

Для тестів існує третє, повністю ізольоване середовище `test` з базою в пам'яті. Pytest вмикає його сам.

## Встановлення

Потрібен Python 3.9 або новіший.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_env.py
```

Скрипт `init_env.py` створює файли `.env.sandbox` і `.env.production` із шаблонів `*.example` та генерує для кожного середовища окремий `SECRET_KEY`. Він також виводить пароль демо-користувачів sandbox, його варто записати. Файли `.env.sandbox` і `.env.production` містять секрети, тому вони в `.gitignore` і в репозиторій не потрапляють.

## Запуск у sandbox

```bash
python -m app.seed                                  # демо-клієнти, тварини, записи (необов'язково)
python -m app.create_admin --email admin@example.com --name "Admin"
uvicorn app.main:app --reload
```

Відкрийте http://127.0.0.1:8000. Документація API: http://127.0.0.1:8000/docs.

Демо-клієнти: `ivan@sandbox.example.com` і `olena@sandbox.example.com`, пароль — значення `SEED_USER_PASSWORD` з `.env.sandbox`.

## Запуск у production (локально)

```bash
APP_ENV=production python -m app.create_admin --email admin@example.com --name "Admin"
APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8000
```

На Windows (PowerShell) змінна задається так: `$env:APP_ENV="production"`, а потім виконуються ті самі команди без префікса.

Production використовує окрему базу, тож адміністратора там треба створити окремо. Користувачі й дані з sandbox у production не видно.

Застосунок навмисно не запуститься, якщо в production:

- не задано `SECRET_KEY` або `DATABASE_URL`;
- `SECRET_KEY` коротший за 32 символи;
- `DEBUG=true`;
- `DATABASE_URL` вказує на базу sandbox або на базу в пам'яті.

## Змінні оточення

| Змінна | Обов'язкова | Опис |
|---|---|---|
| `APP_ENV` | ні | `sandbox` (за замовчуванням), `production` або `test` |
| `DATABASE_URL` | так | рядок підключення до БД; `postgres://...` від хостингу перетворюється на `postgresql+asyncpg://...` автоматично |
| `SECRET_KEY` | так | ключ підпису JWT, мінімум 32 символи, свій для кожного середовища |
| `DEBUG` | ні | режим відладки, за замовчуванням `false`, у production заборонений |
| `DOCS_ENABLED` | ні | показувати `/docs`, за замовчуванням `false` |
| `LOG_LEVEL` | ні | `DEBUG`, `INFO`, `WARNING` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ні | час життя токена, за замовчуванням 60 |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | ні | якщо задані, адміністратор створюється при старті (зручно на хостингу без консолі) |
| `SEED_USER_PASSWORD` | для `app.seed` | пароль демо-користувачів sandbox |

Змінні оточення мають пріоритет над файлом `.env.*`. Саме так налаштування передають хостинг і CI.

## Тести

```bash
pytest -v
```

Тести самі вмикають середовище `test` із базою в пам'яті, тому не чіпають ні sandbox, ні production і не потребують файлів `.env`.

## Навантажувальне тестування

Сценарії Locust лежать у `loadtest/`, план і методика описані в `docs/load-testing.md`.

```bash
pip install -r requirements-loadtest.txt
uvicorn app.main:app                  # термінал 1: sandbox без --reload
python loadtest/run.py baseline       # термінал 2: 50 VUsers, 3 хв
python loadtest/run.py step           # 10 → 150 VUsers, 5 хв
```

Звіт з таблицями, графіками та виявленими вузькими місцями з'являється в `loadtest/results/<профіль>/report.md`.

## CI/CD

Пайплайн `.github/workflows/ci.yml` запускається при кожному пуші в `main` і при кожному Pull Request:

1. **Лінтери**: ті самі перевірки, що й локально перед комітом (`pre-commit`: ruff, ruff-format, пробіли, кінці файлів).
2. **Тести**: `pytest` на Python 3.9 і 3.12.
3. **Деплой**: Render розгортає нову версію production лише після того, як обидва кроки пройшли успішно (`autoDeployTrigger: checksPass` у `render.yaml`).

## Деплой на Render

Інфраструктура описана у файлі `render.yaml`: вебсервіс і безкоштовна база PostgreSQL.

1. Зареєструйтесь на https://render.com через GitHub.
2. Натисніть **New → Blueprint** і виберіть репозиторій `vet-crm`.
3. Render прочитає `render.yaml` і попросить ввести `ADMIN_EMAIL` та `ADMIN_PASSWORD`. Цей адміністратор буде створений при першому запуску.
4. Натисніть **Apply**. `SECRET_KEY` згенерується автоматично, `DATABASE_URL` підставиться з бази.
5. Застосунок буде доступний за адресою виду `https://vet-crm-xxxx.onrender.com`.

Безкоштовний сервіс Render засинає після 15 хвилин без запитів, тому перший запит після паузи може тривати до хвилини.

## Структура проєкту

```
app/
  core/config.py     налаштування середовищ (pydantic-settings)
  core/errors.py     обробка помилок 500 без витоку стектрейсів
  core/deps.py       автентифікація і перевірка прав
  core/security.py   bcrypt і JWT
  core/bootstrap.py  створення адміна зі змінних оточення
  api/               маршрути REST API
  static/            веб-інтерфейс
  models.py          моделі БД
  seed.py            демо-дані для sandbox
  create_admin.py    створення адміністратора з консолі
scripts/init_env.py  генерація .env.sandbox і .env.production
loadtest/            навантажувальне тестування (Locust)
tests/               pytest
.env.*.example       шаблони налаштувань (без секретів)
render.yaml          інфраструктура production на Render
```

Детальніше про авторизацію та ролі: `docs/auth-architecture.md`.
