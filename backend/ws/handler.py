"""
WebSocket handler for the realtime intake protocol.

Message types (client → server):
  {"type":"text","message":"..."}
  {"type":"start"}
  {"type":"stop"}

Message types (server → client):
  {"type":"session_id","id":"..."}
  {"type":"agent_text","text":"..."}
  {"type":"fields_update","fields":{...}}
  {"type":"state_update","current_node":"...","call_complete":bool}
  {"type":"summary","summary":{...}|null}
  {"type":"handoff","handoff_triggered":bool,"severity":"...","reason":"..."}
  {"type":"error","message":"..."}
"""

from typing import Any, Optional

from fastapi import WebSocket

from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.runner import run_turn
from backend.session.manager import session_manager
from backend.session.models import IntakeState


async def handle_intake_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    # Resolve session — "new" creates a fresh one
    if session_id == "new":
        session_id = session_manager.create_session()
        await _send_json(websocket, {"type": "session_id", "id": session_id})
    else:
        session = session_manager.get_session(session_id)
        if session is None:
            await _send_json(
                websocket,
                {"type": "error", "message": f"Session {session_id} not found."},
            )
            await websocket.close()
            return

    session = session_manager.get_or_create_session(session_id)

    try:
        async for raw in websocket.iter_json():
            msg_type = raw.get("type")

            if msg_type == "start":
                await _handle_start(websocket, session)

            elif msg_type == "text":
                await _handle_text(websocket, session, raw.get("message", ""))

            elif msg_type == "stop":
                break

            else:
                await _send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    },
                )
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _handle_start(websocket: WebSocket, session: Any) -> None:
    """Send the initial greeting prompt for a fresh session."""
    node = NODE_REGISTRY.get(session.current_node.value)
    prompt = node.prompt_template if node else ""

    await _send_json(
        websocket,
        {"type": "agent_text", "text": prompt},
    )
    await _send_json(
        websocket,
        {
            "type": "state_update",
            "current_node": session.current_node.value,
            "call_complete": False,
        },
    )
    await _send_json(
        websocket,
        {"type": "fields_update", "fields": _fields_dict(session.extracted_fields)},
    )


async def _handle_text(
    websocket: WebSocket,
    session: Any,
    message: str,
) -> None:
    if session.call_complete:
        await _send_json(
            websocket,
            {"type": "error", "message": "This session is already complete."},
        )
        return

    message = message or ""

    # First turn with empty message — send greeting without running the FSM
    if not message.strip() and session.turn_count == 0:
        await _handle_start(websocket, session)
        return

    session.turn_count += 1
    result = run_turn(
        current_node_name=session.current_node.value,
        message=message,
        fields=session.extracted_fields,
        retry_count_by_node=session.retry_count_by_node,
    )

    new_node = IntakeState(result.next_node) if result.next_node else IntakeState.COMPLETE

    # Persist updated session
    session.current_node = new_node
    session.extracted_fields = result.fields
    session.call_complete = result.call_complete
    if result.retry_count_by_node is not None:
        session.retry_count_by_node = result.retry_count_by_node
    session.handoff_triggered = result.handoff_triggered
    session.red_flag_severity = result.red_flag_severity
    session.red_flag_id = result.red_flag_id
    session.handoff_reason = result.handoff_reason
    session_manager.update_session(session)

    # Send structured responses
    await _send_json(
        websocket,
        {"type": "agent_text", "text": result.assistant_message},
    )
    await _send_json(
        websocket,
        {"type": "fields_update", "fields": _fields_dict(result.fields)},
    )
    await _send_json(
        websocket,
        {
            "type": "state_update",
            "current_node": new_node.value,
            "call_complete": result.call_complete,
        },
    )

    if result.handoff_triggered:
        await _send_json(
            websocket,
            {
                "type": "handoff",
                "handoff_triggered": True,
                "severity": result.red_flag_severity,
                "reason": result.handoff_reason,
            },
        )

    if result.call_complete:
        summary_dict = _summary_dict(result.final_summary) if result.final_summary else None
        await _send_json(
            websocket,
            {"type": "summary", "summary": summary_dict},
        )


async def _send_json(websocket: WebSocket, data: dict[str, Any]) -> None:
    try:
        await websocket.send_json(data)
    except Exception:
        pass


def _fields_dict(fields: Any) -> dict[str, Any]:
    if fields is None:
        return {}
    out = {}
    for name in (
        "patient_name",
        "date_of_birth",
        "chief_complaint",
        "symptoms",
        "symptom_duration",
        "medical_history",
        "allergies",
        "medications",
        "visit_reason",
    ):
        fv = getattr(fields, name, None)
        if fv is not None:
            out[name] = {
                "value": fv.value,
                "confidence": fv.confidence,
                "source_turn_id": fv.source_turn_id,
                "confirmed": fv.confirmed,
            }
    return out


def _summary_dict(summary: Any) -> Optional[dict[str, Optional[str]]]:
    if summary is None:
        return None
    return {
        "patient_name": summary.patient_name,
        "date_of_birth": summary.date_of_birth,
        "chief_complaint": summary.chief_complaint,
        "symptoms": summary.symptoms,
        "symptom_duration": summary.symptom_duration,
        "medical_history": summary.medical_history,
        "allergies": summary.allergies,
        "medications": summary.medications,
        "visit_reason": summary.visit_reason,
    }
