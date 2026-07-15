"""Redis-backed progress store for long-running dataset mutations."""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from uuid import uuid4

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class DatasetOperationStore:
    """Share dataset-operation progress across workers, with an in-memory fallback."""

    def __init__(self) -> None:
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_checked = False

    @staticmethod
    def _key(task_id: str) -> str:
        return f"dataset_operation:{task_id}"

    def _redis_client(self):
        if self._redis_checked:
            return self._redis
        with self._lock:
            if self._redis_checked:
                return self._redis
            self._redis_checked = True
            try:
                import redis

                client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=0.3,
                    socket_timeout=0.5,
                )
                client.ping()
                self._redis = client
                logger.info("数据集任务进度使用 Redis: %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning("Redis 不可用，数据集任务进度降级到进程内存: %s", exc)
                self._redis = None
        return self._redis

    def set(self, task_id: str, data: dict[str, Any]) -> None:
        ttl_seconds = int(settings.DATASET_OPERATION_TTL_SECONDS)
        expires_at = time.time() + ttl_seconds
        payload = dict(data)
        key = self._key(task_id)
        with self._lock:
            self._memory[key] = (expires_at, payload)
        client = self._redis_client()
        if client is not None:
            try:
                client.setex(
                    key,
                    ttl_seconds,
                    json.dumps(payload, ensure_ascii=False),
                )
            except Exception as exc:
                logger.warning("写入 Redis 数据集任务进度失败，继续使用内存: %s", exc)
                self._redis = None

    def update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        payload = self.get(task_id) or {"task_id": task_id}
        payload.update(changes)
        self.set(task_id, payload)
        return payload

    def create(self, *, operation: str, user_id: int, message: str) -> dict[str, Any]:
        task_id = uuid4().hex
        payload = {
            "task_id": task_id,
            "operation": operation,
            "user_id": user_id,
            "status": "pending",
            "progress": 0,
            "message": message,
            "result": None,
        }
        self.set(task_id, payload)
        return payload

    def get(self, task_id: str) -> dict[str, Any] | None:
        key = self._key(task_id)
        client = self._redis_client()
        if client is not None:
            try:
                value = client.get(key)
                if value:
                    return json.loads(value)
            except Exception as exc:
                logger.warning("读取 Redis 数据集任务进度失败，回退到内存: %s", exc)
                self._redis = None
        with self._lock:
            cached = self._memory.get(key)
            if not cached:
                return None
            expires_at, payload = cached
            if expires_at < time.time():
                self._memory.pop(key, None)
                return None
            return dict(payload)


dataset_operation_store = DatasetOperationStore()
