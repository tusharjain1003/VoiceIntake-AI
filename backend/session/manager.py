"""
Re-export the active session manager.

When ``settings.dev_mode`` is True and Redis is unavailable, falls back to
an in-memory store. In production mode, ``SessionStoreUnavailableError`` is
raised so callers can respond with HTTP 503 / WS error.
"""

import logging
from typing import Optional, Protocol

from backend.config import settings
from backend.session.exceptions import SessionStoreUnavailableError
from backend.session.models import SessionData

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    """Interface implemented by RedisSessionManager and MemorySessionManager."""

    async def check_available(self) -> bool: ...

    async def create_session(self) -> str: ...

    async def get_or_create_session(self, session_id: str) -> SessionData: ...

    async def get_session(self, session_id: str) -> Optional[SessionData]: ...

    async def update_session(self, session: SessionData) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...


async def _get_session_store() -> SessionStore:
    from backend.session.redis_manager import RedisSessionManager

    redis_mgr = RedisSessionManager()
    if await redis_mgr.check_available():
        logger.info("Using Redis session store")
        return redis_mgr

    if settings.dev_mode:
        from backend.session.memory_manager import MemorySessionManager

        logger.warning(
            "Redis unavailable — falling back to in-memory session store (dev_mode=True). "
            "Sessions will not persist across restarts."
        )
        return MemorySessionManager()

    raise SessionStoreUnavailableError(
        "Redis is unavailable and dev_mode is False. "
        "Start Redis (docker-compose up -d) or set DEV_MODE=true for local development."
    )


session_manager: SessionStore | None = None


async def init_session_manager() -> None:
    global session_manager
    session_manager = await _get_session_store()


__all__ = ["session_manager", "init_session_manager", "SessionStoreUnavailableError"]
