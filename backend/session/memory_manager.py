"""
In-memory session manager for local development when Redis is unavailable.

Controlled by the ``dev_mode`` setting — never used in production.
"""

import logging
import uuid
from typing import Optional

from backend.session.exceptions import SessionStoreUnavailableError
from backend.session.models import SessionData

logger = logging.getLogger(__name__)


class MemorySessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    async def check_available(self) -> bool:
        return True

    async def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionData(session_id=session_id)
        return session_id

    async def get_or_create_session(self, session_id: str) -> SessionData:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        session = SessionData(session_id=session_id)
        self._sessions[session_id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        return self._sessions.get(session_id)

    async def list_recent_sessions(self, limit: int = 20) -> list[SessionData]:
        return list(reversed(list(self._sessions.values())))[0:limit]

    async def update_session(self, session: SessionData) -> None:
        if session.session_id not in self._sessions:
            raise SessionStoreUnavailableError(
                f"Session {session.session_id} not found in memory store."
            )
        self._sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
