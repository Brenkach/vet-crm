"""Кеш на Redis (ЛР №7).

Принципи:
- кеш необов'язковий: без REDIS_URL або з CACHE_ENABLED=false усі звернення — «промахи»;
- кеш не може зламати застосунок: якщо Redis недоступний, помилка записується в лог,
  а дані беруться з БД;
- кожен ключ має TTL, тож навіть пропущена інвалідація виправиться сама;
- при зміні даних відповідні ключі видаляються одразу (інвалідація).
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("vet_crm.cache")

PREFIX = "vetcrm:"
# Після помилки з'єднання Redis не опитується кілька секунд, щоб не гальмувати кожен запит тайм-аутом
RETRY_AFTER_ERROR_S = 5.0


def user_key(user_id: int) -> str:
    return f"user:{user_id}"


def pets_key(owner_id: int) -> str:
    return f"pets:{owner_id}"


STATS_KEY = "admin:stats"


class Cache:
    def __init__(self) -> None:
        self.client = None
        self._down_until = 0.0
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def configure(self, url: Optional[str], enabled: bool = True) -> None:
        if not (url and enabled):
            self.client = None
            return
        import redis.asyncio as redis

        self.client = redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)

    def _available(self) -> bool:
        return self.client is not None and time.monotonic() >= self._down_until

    def _failed(self, exc: Exception) -> None:
        self._down_until = time.monotonic() + RETRY_AFTER_ERROR_S
        logger.warning("Redis недоступний (%s) — %.0f с працюємо без кешу", exc, RETRY_AFTER_ERROR_S)

    async def get(self, key: str) -> Optional[Any]:
        if not self._available():
            return None
        try:
            raw = await self.client.get(PREFIX + key)
        except Exception as exc:  # будь-яка проблема з Redis = промах кешу
            self._failed(exc)
            return None
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        if not self._available():
            return
        try:
            await self.client.set(PREFIX + key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception as exc:
            self._failed(exc)

    async def delete(self, *keys: str) -> None:
        if not keys or not self._available():
            return
        try:
            await self.client.delete(*(PREFIX + k for k in keys))
        except Exception as exc:
            self._failed(exc)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()


cache = Cache()
