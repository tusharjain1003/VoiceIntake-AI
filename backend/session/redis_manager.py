"""
Redis-backed session manager.

Stores active session state as JSON in Redis with a configurable TTL.
All methods are async. Falls back gracefully when Redis is unavailable
(logs warning, returns None for lookups).
"""

import json
import logging
import uuid
from typing import Optional

from backend.config import settings
from backend.database import redis_client
from backend.session.models import SessionData

logger = logging.getLogger(__name__)

_SESSION_KEY_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{session_id}"


class RedisSessionManager:
    async def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        session = SessionData(session_id=session_id)
        await self._save(session)
        return session_id

    async def get_or_create_session(self, session_id: str) -> SessionData:
        existing = await self.get_session(session_id)
        if existing is not None:
            return existing
        session = SessionData(session_id=session_id)
        await self._save(session)
        return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        raw = await self._load(session_id)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return SessionData.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to deserialize session %s: %s", session_id, exc)
            return None

    async def update_session(self, session: SessionData) -> None:
        await self._save(session)

    async def delete_session(self, session_id: str) -> None:
        try:
            if redis_client is not None:
                await redis_client.delete(_key(session_id))
        except Exception as exc:
            logger.warning("Failed to delete session %s from Redis: %s", session_id, exc)

    async def _save(self, session: SessionData) -> None:
        try:
            if redis_client is None:
                logger.debug(
                    "Redis not available — skipping save for session %s", session.session_id
                )
                return
            raw = session.model_dump_json()
            await redis_client.setex(
                _key(session.session_id),
                settings.session_ttl_seconds,
                raw,
            )
        except Exception as exc:
            logger.warning("Failed to save session %s to Redis: %s", session.session_id, exc)

    async def _load(self, session_id: str) -> Optional[str]:
        try:
            if redis_client is None:
                return None
            return await redis_client.get(_key(session_id))
        except Exception as exc:
            logger.warning("Failed to load session %s from Redis: %s", session_id, exc)
            return None


session_manager = RedisSessionManager()
