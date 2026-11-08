# syntax=docker/dockerfile:1

# Версія Python для обох етапів (має збігатися, бо віртуальне оточення копіюється між ними)
ARG PYTHON_VERSION=3.12

# ---------- Етап 1: builder ----------
# Компілятор і кеш pip потрібні лише тут. У фінальний образ потрапить тільки готове віртуальне оточення.
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Компілятор — для пакетів, які не мають готових wheel під цю платформу
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Спочатку лише requirements.txt: шар із залежностями кешується і не перезбирається при зміні коду
COPY requirements.txt .
RUN pip install -r requirements.txt


# ---------- Етап 2: runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Застосунок працює від звичайного користувача, а не від root
RUN useradd --create-home --uid 1000 app


WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Спочатку міграції БД, потім команда з CMD
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
