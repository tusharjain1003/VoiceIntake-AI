"""
Redis-backed session manager.

Stores active session state as JSON in Redis with a configurable TTL.
Raises SessionStoreUnavailableError when Redis is unreachable.
"""

import json
import logging
import uuid
from typing import Optional

from backend.config import settings
from backend.database import redis_client
from backend.session.exceptions import SessionStoreUnavailableError
from backend.session.models import SessionData

logger = logging.getLogger(__name__)

_SESSION_KEY_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{session_id}"


class RedisSessionManager:
    async def check_available(self) -> bool:
        if redis_client is None:
            return False
        try:
            await redis_client.ping()
            return True
        except Exception:
            return False

    async def create_session(self) -> str:
        if redis_client is None:
            raise SessionStoreUnavailableError("Redis is not connected — cannot create session.")
        session_id = str(uuid.uuid4())
        session = SessionData(session_id=session_id)
        await self._save(session)
        return session_id

    async def get_or_create_session(self, session_id: str) -> SessionData:
        if redis_client is None:
            raise SessionStoreUnavailableError(
                "Redis is not connected — cannot load or create session."
            )
        existing = await self.get_session(session_id)
        if existing is not None:
            return existing
        session = SessionData(session_id=session_id)
        await self._save(session)
        return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        if redis_client is None:
            raise SessionStoreUnavailableError("Redis is not connected — cannot load session.")
        raw = await self._load(session_id)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return SessionData.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to deserialize session %s: %s", session_id, exc)
            return None

    async def list_recent_sessions(self, limit: int = 20) -> list[SessionData]:
        if redis_client is None:
            raise SessionStoreUnavailableError("Redis is not connected — cannot list sessions.")
        try:
            keys = await redis_client.keys(f"{_SESSION_KEY_PREFIX}*")
        except Exception as exc:
            raise SessionStoreUnavailableError(
                f"Failed to list sessions from Redis: {exc}"
            ) from exc

        sessions: list[SessionData] = []
        for key in keys:
            session_id = str(key).removeprefix(_SESSION_KEY_PREFIX)
            session = await self.get_session(session_id)
            if session is not None:
                sessions.append(session)

        sessions.sort(key=lambda session: session.turn_count, reverse=True)
        return sessions[:limit]

    async def update_session(self, session: SessionData) -> None:
        if redis_client is None:
            raise SessionStoreUnavailableError("Redis is not connected — cannot update session.")
        await self._save(session)

    async def delete_session(self, session_id: str) -> None:
        if redis_client is None:
            raise SessionStoreUnavailableError("Redis is not connected — cannot delete session.")
        try:
            await redis_client.delete(_key(session_id))
        except Exception as exc:
            logger.warning("Failed to delete session %s from Redis: %s", session_id, exc)

    async def _save(self, session: SessionData) -> None:
        try:
            raw = session.model_dump_json()
            await redis_client.setex(
                _key(session.session_id),
                settings.session_ttl_seconds,
                raw,
            )
        except Exception as exc:
            raise SessionStoreUnavailableError(
                f"Failed to save session {session.session_id} to Redis: {exc}"
            ) from exc

    async def _load(self, session_id: str) -> Optional[str]:
        try:
            return await redis_client.get(_key(session_id))
        except Exception as exc:
            raise SessionStoreUnavailableError(
                f"Failed to load session {session_id} from Redis: {exc}"
            ) from exc
