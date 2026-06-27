import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.session.models import SessionData


class InMemorySessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}
        self._timestamps: dict[str, datetime] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionData(session_id=session_id)
        self._timestamps[session_id] = datetime.now(tz=timezone.utc)
        return session_id

    def get_or_create_session(self, session_id: str) -> SessionData:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        new_session = SessionData(session_id=session_id)
        self._sessions[session_id] = new_session
        self._timestamps[session_id] = datetime.now(tz=timezone.utc)
        return new_session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        return self._sessions.get(session_id)

    def update_session(self, session: SessionData) -> None:
        self._sessions[session.session_id] = session
        self._timestamps[session.session_id] = datetime.now(tz=timezone.utc)

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._timestamps.pop(session_id, None)


session_manager = InMemorySessionManager()
