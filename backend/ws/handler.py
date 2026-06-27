"""
WebSocket handler for the realtime intake protocol.

Message types (client -> server):
  {"type":"text","message":"..."}
  {"type":"start"}
  {"type":"stop"}
  Binary frames (WebM/Opus audio chunks via MediaRecorder)

Message types (server -> client):
  {"type":"session_id","id":"..."}
  {"type":"agent_text","text":"..."}
  {"type":"fields_update","fields":{...}}
  {"type":"state_update","current_node":"...","call_complete":bool}
  {"type":"summary","summary":{...}|null}
  {"type":"handoff","handoff_triggered":bool,"severity":"...","reason":"..."}
  {"type":"audio_debug","bytes_received":int}
  {"type":"transcript","text":"...","is_final":bool}
  {"type":"tts_start","content_type":"audio/mpeg"}
  {"type":"tts_end"}
  {"type":"latency","turn_id":"...","metrics":{...}}
  {"type":"error","message":"..."}
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional

from fastapi import WebSocket

from backend.config import settings
from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.runner import run_turn
from backend.rag.enrich import enrich_summary_with_rag
from backend.session.manager import session_manager
from backend.session.models import IntakeState
from backend.tracking.latency import TurnTiming
from backend.voice.deepgram_client import DeepgramStreamClient
from backend.voice.tts_client import synthesize

logger = logging.getLogger(__name__)

_AUDIO_DEBUG_INTERVAL = 5


async def handle_intake_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    if session_id == "new":
        session_id = await session_manager.create_session()
        await _send_json(websocket, {"type": "session_id", "id": session_id})
    else:
        session = await session_manager.get_session(session_id)
        if session is None:
            await _send_json(
                websocket,
                {"type": "error", "message": f"Session {session_id} not found."},
            )
            await websocket.close()
            return

    session = await session_manager.get_or_create_session(session_id)

    dg: Optional[DeepgramStreamClient] = None
    _dg_started = False
    timing = TurnTiming()

    audio_bytes = 0
    last_debug_ts = time.monotonic()

    try:
        while True:
            ws_task = asyncio.create_task(websocket.receive())
            dg_task = asyncio.create_task(dg.read_event()) if dg and dg.available else None

            tasks = [t for t in (ws_task, dg_task) if t is not None]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            now = time.monotonic()

            if dg_task and dg_task in done:
                await _handle_dg_event(websocket, session, dg_task.result(), timing)

            if ws_task in done:
                event = ws_task.result()

                if "bytes" in event:
                    chunk = event["bytes"]
                    audio_bytes += len(chunk)
                    timing.set_first_chunk(now)

                    if settings.deepgram_api_key and not _dg_started:
                        _dg_started = True
                        dg = DeepgramStreamClient(
                            api_key=settings.deepgram_api_key,
                            model=settings.deepgram_model,
                            language=settings.deepgram_language,
                        )
                        asyncio.create_task(dg.start())

                    if dg and dg.available:
                        await dg.send(chunk)

                    if now - last_debug_ts >= _AUDIO_DEBUG_INTERVAL:
                        await _send_json(
                            websocket,
                            {"type": "audio_debug", "bytes_received": audio_bytes},
                        )
                        last_debug_ts = now

                elif "text" in event:
                    try:
                        raw = json.loads(event["text"])
                    except json.JSONDecodeError:
                        await _send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                        continue

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
                            {"type": "error", "message": f"Unknown message type: {msg_type}"},
                        )

            for task in pending:
                task.cancel()

    except Exception:
        pass
    finally:
        if dg:
            await dg.close()
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Deepgram event handler
# ---------------------------------------------------------------------------


async def _handle_dg_event(
    websocket: WebSocket,
    session: Any,
    event: tuple,
    timing: Optional[TurnTiming] = None,
) -> None:
    event_type = event[0]

    if event_type == "transcript":
        _, text, is_final = event
        if not text.strip():
            return
        if is_final:
            if timing:
                timing.stt_final_time = time.monotonic()
                timing.start_turn()
            await _handle_text(websocket, session, text, timing)
        else:
            await _send_json(websocket, {"type": "transcript", "text": text, "is_final": False})

    elif event_type == "error":
        await _send_json(websocket, {"type": "error", "message": "STT unavailable"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _handle_start(websocket: WebSocket, session: Any) -> None:
    """Send the initial greeting prompt for a fresh session."""
    node = NODE_REGISTRY.get(session.current_node.value)
    prompt = node.prompt_template if node else ""

    await _send_json(websocket, {"type": "agent_text", "text": prompt})
    await _send_tts(websocket, prompt, session)
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
    timing: Optional[TurnTiming] = None,
) -> None:
    if session.call_complete:
        await _send_json(
            websocket, {"type": "error", "message": "This session is already complete."}
        )
        return

    message = message or ""

    if not message.strip() and session.turn_count == 0:
        await _handle_start(websocket, session)
        return

    session.turn_count += 1

    if timing:
        timing.fsm_start = time.monotonic()

    result = run_turn(
        current_node_name=session.current_node.value,
        message=message,
        fields=session.extracted_fields,
        retry_count_by_node=session.retry_count_by_node,
    )

    if timing:
        timing.fsm_end = time.monotonic()

    new_node = IntakeState(result.next_node) if result.next_node else IntakeState.COMPLETE

    session.current_node = new_node
    session.extracted_fields = result.fields
    session.call_complete = result.call_complete
    if result.retry_count_by_node is not None:
        session.retry_count_by_node = result.retry_count_by_node
    session.handoff_triggered = result.handoff_triggered
    session.red_flag_severity = result.red_flag_severity
    session.red_flag_id = result.red_flag_id
    session.handoff_reason = result.handoff_reason
    await session_manager.update_session(session)

    await _send_json(websocket, {"type": "agent_text", "text": result.assistant_message})

    if timing:
        timing.tts_start = time.monotonic()
    await _send_tts(websocket, result.assistant_message, session, timing)

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

    if result.call_complete and result.final_summary:
        await enrich_summary_with_rag(result.final_summary, result.fields)
        summary_dict = _summary_dict(result.final_summary)
        await _send_json(websocket, {"type": "summary", "summary": summary_dict})


async def _send_latency(
    websocket: WebSocket,
    session: Any,
    timing: TurnTiming,
) -> None:
    """Record the completed turn and send a latency event to the frontend."""
    client_data = timing.to_client_dict()
    await _send_json(websocket, {"type": "latency", **client_data})
    session.latency_logs.append({"turn_number": timing.turn_counter, **client_data["metrics"]})
    await session_manager.update_session(session)
    timing.reset_utterance()


async def _send_tts(
    websocket: WebSocket,
    text: str,
    session: Any,
    timing: Optional[TurnTiming] = None,
) -> None:
    """Synthesise TTS and send audio frames (best-effort; failures are logged)."""
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        return
    audio = await asyncio.to_thread(
        synthesize,
        text,
        settings.elevenlabs_api_key,
        settings.elevenlabs_voice_id,
        settings.elevenlabs_model,
    )
    if audio is None:
        return

    if timing:
        timing.tts_end = time.monotonic()

    await _send_json(websocket, {"type": "tts_start", "content_type": "audio/mpeg"})
    try:
        await websocket.send_bytes(audio)
    except Exception:
        pass
    await _send_json(websocket, {"type": "tts_end"})

    if timing:
        timing.tts_end = time.monotonic()
        await _send_latency(websocket, session, timing)


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


def _summary_dict(summary: Any) -> Optional[dict[str, Any]]:
    if summary is None:
        return None
    out: dict[str, Any] = {
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
    ctx = getattr(summary, "clinician_context", None)
    if ctx:
        out["clinician_context"] = ctx
    return out
