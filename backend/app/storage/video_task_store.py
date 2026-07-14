"""Small Redis-backed progress store for asynchronous video detection tasks."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class VideoTaskStore:
    """Keep progress in Redis when available and always retain a local fallback."""

    def __init__(self) -> None:
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_checked = False

    @staticmethod
    def _key(task_id: int) -> str:
        return f"video_task:{task_id}"

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
                logger.info("视频任务进度使用 Redis: %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning("Redis 不可用，视频任务进度降级到进程内存: %s", exc)
                self._redis = None
        return self._redis

    def set(self, task_id: int, data: dict[str, Any]) -> None:
        expires_at = time.time() + settings.VIDEO_TASK_TTL_SECONDS
        payload = dict(data)
        with self._lock:
            self._memory[self._key(task_id)] = (expires_at, payload)
        client = self._redis_client()
        if client is not None:
            try:
                client.setex(
                    self._key(task_id),
                    settings.VIDEO_TASK_TTL_SECONDS,
                    json.dumps(payload, ensure_ascii=False),
                )
            except Exception as exc:
                logger.warning("写入 Redis 视频任务进度失败，继续使用内存: %s", exc)
                self._redis = None

    def get(self, task_id: int) -> dict[str, Any] | None:
        client = self._redis_client()
        if client is not None:
            try:
                value = client.get(self._key(task_id))
                if value:
                    return json.loads(value)
            except Exception as exc:
                logger.warning("读取 Redis 视频任务进度失败，回退到内存: %s", exc)
                self._redis = None
        with self._lock:
            cached = self._memory.get(self._key(task_id))
            if not cached:
                return None
            expires_at, payload = cached
            if expires_at < time.time():
                self._memory.pop(self._key(task_id), None)
                return None
            return dict(payload)


video_task_store = VideoTaskStore()
