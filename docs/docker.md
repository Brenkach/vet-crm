# Контейнеризація (ЛР №5)

> У ЛР №6 перед застосунком з'явився балансувальник Nginx і кілька реплік — актуальна схема в `docs/load-balancing.md`. Тепер єдина точка входу — http://localhost (порт `HTTP_PORT`), а порт застосунку назовні не публікується.

## Архітектура

```
              ваш комп'ютер
                   │  http://localhost:8000
┌──────────────────┼───────────────────────────────────────────┐
│ Docker           │                                           │
│        мережа frontend                                       │
│                  │                                           │
│          ┌───────┴───────┐        ┌──────────────────┐       │
│          │      app      │        │        db        │       │
│          │ FastAPI +     │───────▶│  PostgreSQL 16   │       │
│          │ uvicorn       │  5432  │                  │       │
│          └───────────────┘        └────────┬─────────┘       │
│        мережа backend (internal: без доступу в інтернет)     │
│                                            │                 │
│                                   том postgres_data          │
└────────────────────────────────────────────┼─────────────────┘
                                             ▼
                                 дані зберігаються на диску
```

| Файл | Призначення |
|---|---|
| `Dockerfile` | багатоетапне збирання образу застосунку |
| `.dockerignore` | що не потрапляє в образ |
| `docker/entrypoint.sh` | при старті контейнера: міграції БД, потім сервер |
| `docker-compose.yml` | оркестрація: застосунок + PostgreSQL, мережі, том, healthcheck |
| `docker-compose.dev.yml` | режим розробки з hot-reload |
| `.env.docker.example` | шаблон змінних оточення; робочий `.env` створює `scripts/init_env.py` |
| `alembic.ini`, `migrations/` | міграції схеми бази даних |

## 1. Dockerfile

**Базовий образ `python:3.12-slim`.** Debian-образ без зайвих пакетів, близько 50 МБ. Alpine менший, але використовує бібліотеку musl замість glibc, тому для `asyncpg`, `bcrypt` і `greenlet` готові пакети (wheels) часто не підходять і їх доводиться компілювати. Slim-образ є компромісом між розміром і сумісністю.

**Робоча директорія:** `WORKDIR /app`.

**Порядок шарів.** Спочатку копіюється лише `requirements.txt` і встановлюються залежності, а потім код. Docker кешує шари, тож при зміні коду залежності не перевстановлюються, і повторне збирання займає секунди.

**Безпека.** Застосунок працює від користувача `app`, а не від root. Секрети в образ не потрапляють: `.env*` виключені в `.dockerignore`, а змінні оточення передаються під час запуску.

**Команда запуску:** `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Перед нею `docker/entrypoint.sh` виконує `alembic upgrade head`. `exec` у скрипті робить uvicorn головним процесом контейнера, тож при `docker compose down` він коректно отримує сигнал зупинки.

**HEALTHCHECK** кожні 10 секунд звертається до `/health`, і Docker показує стан контейнера `healthy` або `unhealthy`.

## 2. `.dockerignore`

В образ потрапляють лише `app/`, `migrations/`, `alembic.ini`, `docker/` і `requirements.txt`. Виключено:

| Що | Чому |
|---|---|
| `.git`, `.github`, `.pre-commit-config.yaml` | історія і CI не потрібні для роботи |
| `.venv`, `__pycache__`, `*.pyc`, `.pytest_cache`, `.ruff_cache` | локальні оточення і кеші; залежності встановлюються в образі заново |
| `.idea`, `.vscode`, `.DS_Store` | файли IDE та ОС |
| `*.log`, `*.db` | логи і локальні бази SQLite |
| `.env`, `.env.*` | секрети не вшиваються в образ |
| `tests/`, `loadtest/`, `docs/`, `requirements-dev.txt` | потрібні розробнику, а не застосунку |

Залежності розділено: `requirements.txt` містить лише те, що потрібно застосунку, а pytest і httpx винесено в `requirements-dev.txt`, тож вони теж не потрапляють в образ.

## 3. База даних і збереження даних

- Офіційний образ **`postgres:16-alpine`**.
- Дані лежать в іменованому томі **`postgres_data`**, підключеному до `/var/lib/postgresql/data`. Том існує окремо від контейнера: `docker compose down` видаляє контейнери, але не том, тож після нового `up` усі дані на місці. Видалити дані можна лише явно: `docker compose down -v`.
- Порт БД **не публікується** на хост: до PostgreSQL можна достукатися тільки з внутрішньої мережі Docker.

## 4. docker-compose.yml

**Змінні оточення з `.env`.** Compose автоматично читає `.env` для підстановки `${...}` (пароль БД потрапляє і в контейнер `db`, і в рядок підключення застосунку), а директива `env_file: .env` передає змінні в контейнер застосунку. Обов'язкові змінні записані як `${POSTGRES_PASSWORD:?...}`: якщо їх немає, compose відмовиться запускатися з поясненням.

**Мережі.**
- `backend` (`internal: true`) — внутрішня мережа без виходу в інтернет. У ній живуть БД і застосунок. Застосунок звертається до БД за іменем сервісу `db`.
- `frontend` — через неї публікується порт застосунку на хост.

БД підключена лише до `backend`, тож ззовні вона недосяжна, і сама не може нікуди звертатися.

**Черговість запуску.** PostgreSQL перевіряється командою `pg_isready` кожні 5 секунд. Застосунок має `depends_on: db: condition: service_healthy`, тобто стартує лише тоді, коли БД **готова приймати з'єднання**, а не просто запущена. Без цього міграції падали б, бо PostgreSQL ініціалізується кілька секунд після старту контейнера.

**Міграції.** Схему бази створює Alembic (`alembic upgrade head` у `entrypoint.sh`), а не застосунок (`AUTO_CREATE_TABLES=false`). Alembic записує поточну версію схеми в таблицю `alembic_version`, тож при повторному запуску вже застосовані міграції не виконуються. Тест `tests/test_migrations.py` перевіряє, що міграції повністю відповідають моделям.

## 5. Запуск і перевірка

```bash
python3 scripts/init_env.py
docker compose up --build
```

У логах має з'явитися:

```
db-1   | database system is ready to accept connections
app-1  | ==> Застосування міграцій бази даних (alembic upgrade head)
app-1  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Початкова схема...
app-1  | ... Запуск у середовищі production, БД: postgresql+asyncpg://vet_crm:***@db:5432/vet_crm
app-1  | ... Створено адміністратора admin@example.com
app-1  | INFO:     Application startup complete.
```

Перевірки в другому терміналі:

```bash
docker compose ps                                   # обидва сервіси: healthy
curl http://localhost/health                        # {"status":"ok","environment":"production","instance":"..."}
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
                                                    # таблиці users, pets, appointments, alembic_version
```

**Збереження даних:** зареєструйтесь у застосунку, виконайте `docker compose down`, потім `docker compose up -d`. Користувач залишився. Після `docker compose down -v` база порожня.

Те саме автоматично перевіряє CI (job «Docker» у `.github/workflows/ci.yml`) при кожному пуші: збирання, запуск з очікуванням healthcheck, запити до API, таблиці в PostgreSQL, збереження даних після перезапуску.

## 6. Багатоетапне збирання (multi-stage build)

| Етап | Що містить |
|---|---|
| `builder` | компілятор `build-essential`, pip, віртуальне оточення `/opt/venv` з усіма залежностями |
| `runtime` | чистий `python:3.12-slim` + скопійоване `/opt/venv` + код |

У фінальний образ не потрапляють компілятор, заголовкові файли, кеш apt і pip. Порівняти розміри:

```bash
docker build --target builder -t vet-crm:builder .
docker image ls | grep vet-crm
```

## 7. Режим розробки з hot-reload

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

`docker-compose.dev.yml` доповнює основний файл:

- **bind mount** `./app:/app/app` і `./migrations:/app/migrations`: контейнер бачить код безпосередньо з диска, а не копію в образі;
- uvicorn запускається з `--reload` і перезапускається при кожній зміні файлу, без перезбирання образу;
- `WATCHFILES_FORCE_POLLING=true` — надійне відстеження змін через bind mount на macOS і Windows;
- `APP_ENV=sandbox`, `DEBUG=true`, `/docs` увімкнено;
- окрема назва проєкту `vet-crm-dev`: власні контейнери і **власний том БД**, тож дані розробки не змішуються з production-даними з лаби 3.

Перевірка: змініть текст у `app/api/home.py`, збережіть файл, і в логах з'явиться `WatchFiles detected changes ... Reloading`. Наступний запит уже поверне новий текст.

## Нова міграція

Після зміни моделей:

```bash
alembic revision --autogenerate -m "опис змін"
```

Нова міграція застосується автоматично під час наступного запуску контейнера.
