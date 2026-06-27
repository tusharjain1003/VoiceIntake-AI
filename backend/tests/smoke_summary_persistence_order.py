"""
Smoke test: final summaries are enriched before Postgres summary persistence.

The REST and WebSocket completion paths both import ``enrich_summary_with_rag``
directly, so this test monkeypatches each module's imported symbol and verifies
that ``repo.save_summary`` receives the enriched clinician_context payload.
"""

import asyncio
from typing import Any

from fastapi.testclient import TestClient


class _MemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._counter = 0

    async def check_available(self) -> bool:
        return True

    async def create_session(self) -> str:
        from backend.session.models import SessionData

        self._counter += 1
        session_id = f"summary-order-{self._counter}"
        self._sessions[session_id] = SessionData(session_id=session_id)
        return session_id

    async def get_or_create_session(self, session_id: str) -> Any:
        from backend.session.models import SessionData

        if session_id not in self._sessions:
            self._sessions[session_id] = SessionData(session_id=session_id)
        return self._sessions[session_id]

    async def get_session(self, session_id: str) -> Any:
        return self._sessions.get(session_id)

    async def list_recent_sessions(self, limit: int = 20) -> list[Any]:
        return list(self._sessions.values())[-limit:]

    async def update_session(self, session: Any) -> None:
        self._sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


async def _enrich(summary: Any, _fields: Any) -> None:
    summary.clinician_context = {"rag_status": "success", "source": "smoke-test"}


def _messages_to_complete() -> list[str]:
    return [
        "Alex Rivera",
        "03/14/1985",
        "Annual checkup.",
        "No symptoms.",
        "No significant medical history.",
        "No known allergies.",
        "No medications.",
        "Employer-required physical.",
        "yes",
        "",
    ]


def test_rest_summary_saved_after_enrichment() -> None:
    import backend.db.repository as repo_mod
    import backend.main as main_mod
    import backend.session.manager as session_mgr
    from backend.main import app

    saved_summaries: list[dict[str, Any]] = []
    store = _MemorySessionStore()

    async def save_summary(_session_id: str, summary_data: dict[str, Any]) -> bool:
        saved_summaries.append(summary_data)
        return True

    original_store = session_mgr.session_manager
    original_enrich = main_mod.enrich_summary_with_rag
    original_save_summary = repo_mod.save_summary
    session_mgr.session_manager = store
    main_mod.enrich_summary_with_rag = _enrich
    repo_mod.save_summary = save_summary

    try:
        client = TestClient(app)
        session_id = "new"
        final_response = None
        for message in _messages_to_complete():
            response = client.post(f"/text/intake/{session_id}", json={"message": message})
            assert response.status_code == 200
            final_response = response.json()
            session_id = final_response["session_id"]
            if final_response["call_complete"]:
                break

        assert final_response is not None
        assert final_response["call_complete"] is True
        assert saved_summaries
        assert saved_summaries[-1]["clinician_context"] == {
            "rag_status": "success",
            "source": "smoke-test",
        }
    finally:
        session_mgr.session_manager = original_store
        main_mod.enrich_summary_with_rag = original_enrich
        repo_mod.save_summary = original_save_summary


async def _test_ws_summary_saved_after_enrichment() -> None:
    import backend.ws.handler as ws_mod
    from backend.session.models import SessionData

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, Any]] = []

        async def send_json(self, data: dict[str, Any]) -> None:
            self.messages.append(data)

    saved_summaries: list[dict[str, Any]] = []

    async def save_summary(_session_id: str, summary_data: dict[str, Any]) -> bool:
        saved_summaries.append(summary_data)
        return True

    original_enrich = ws_mod.enrich_summary_with_rag
    original_save_summary = ws_mod.repo.save_summary
    original_tts = ws_mod._send_tts
    ws_mod.enrich_summary_with_rag = _enrich
    ws_mod.repo.save_summary = save_summary
    ws_mod._send_tts = _noop_tts

    try:
        websocket = FakeWebSocket()
        store = _MemorySessionStore()
        session = SessionData(session_id="ws-summary-order")
        store._sessions[session.session_id] = session

        for message in _messages_to_complete():
            await ws_mod._handle_text(websocket, session, message, store)
            if session.call_complete:
                break

        assert session.call_complete is True
        assert saved_summaries
        assert saved_summaries[-1]["clinician_context"] == {
            "rag_status": "success",
            "source": "smoke-test",
        }
        summary_events = [msg for msg in websocket.messages if msg.get("type") == "summary"]
        assert summary_events
        assert summary_events[-1]["summary"]["clinician_context"] == {
            "rag_status": "success",
            "source": "smoke-test",
        }
    finally:
        ws_mod.enrich_summary_with_rag = original_enrich
        ws_mod.repo.save_summary = original_save_summary
        ws_mod._send_tts = original_tts


async def _noop_tts(*_args: Any, **_kwargs: Any) -> None:
    return None


def test_ws_summary_saved_after_enrichment() -> None:
    asyncio.run(_test_ws_summary_saved_after_enrichment())


if __name__ == "__main__":
    test_rest_summary_saved_after_enrichment()
    test_ws_summary_saved_after_enrichment()
    print("Summary persistence order smoke checks passed.")
