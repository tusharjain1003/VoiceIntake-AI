"""
WebSocket handler for the realtime intake protocol.

Message types (client -> server):
  {"type":"text","message":"..."}
  {"type":"start"}
  {"type":"stop"}
  {"type":"voice_start"}
  {"type":"voice_stop"}
  Binary frames (WebM/Opus audio chunks via MediaRecorder)

Message types (server -> client):
  {"type":"session_id","id":"..."}
  {"type":"agent_text","text":"..."}
  {"type":"fields_update","fields":{...}}
  {"type":"state_update","current_node":"...","call_complete":bool}
  {"type":"summary","summary":{...}|null}
  {"type":"handoff","handoff_triggered":bool,"severity":"...","reason":"..."}
  {"type":"audio_debug","chunks_received":int,"bytes_received":int,"chunks_forwarded":int,...}
  {"type":"transcript","text":"...","is_final":bool}
  {"type":"tts_start","content_type":"audio/mpeg"}
  {"type":"tts_end"}
  {"type":"latency","turn_id":"...","metrics":{...}}
  {"type":"error","code":"...","message":"..."}
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.db import repository as repo
from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.runner import run_turn
from backend.rag.enrich import enrich_summary_with_rag
from backend.session.exceptions import SessionStoreUnavailableError
from backend.session.manager import SessionStore
from backend.session.models import IntakeState
from backend.tracing.langsmith import Trace
from backend.tracking.latency import TurnTiming
from backend.voice.deepgram_client import DeepgramStreamClient
from backend.voice.tts_client import synthesize

logger = logging.getLogger(__name__)

_DEBUG_INTERVAL = 3
_KEEPALIVE_INTERVAL = 4


@dataclass
class DgStats:
    deepgram_connected_at: float = 0.0
    audio_chunks_received: int = 0
    audio_bytes_received: int = 0
    audio_chunks_queued: int = 0
    audio_bytes_queued: int = 0
    audio_chunks_flushed: int = 0
    audio_bytes_flushed: int = 0
    audio_chunks_forwarded: int = 0
    audio_bytes_forwarded: int = 0
    last_audio_chunk_at: float = 0.0
    transcript_events_received: int = 0
    final_transcripts_received: int = 0
    keepalives_sent: int = 0
    deepgram_close_code: Optional[int] = None
    deepgram_close_reason: str = ""


# ---------------------------------------------------------------------------
# KeepAlive background loop
# ---------------------------------------------------------------------------


async def _keepalive_loop(
    dg: DeepgramStreamClient,
    stats: DgStats,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_KEEPALIVE_INTERVAL)
            break
        except asyncio.TimeoutError:
            if dg and dg.connected and not dg.closed:
                await dg.send_keepalive()
                stats.keepalives_sent += 1


# ---------------------------------------------------------------------------
# Main WebSocket handler
# ---------------------------------------------------------------------------


async def handle_intake_ws(
    websocket: WebSocket,
    session_id: str,
    session_store: SessionStore,
) -> None:
    await websocket.accept()

    try:
        if session_id == "new":
            session_id = await session_store.create_session()
            await _send_json(websocket, {"type": "session_id", "id": session_id})
        else:
            session = None
            try:
                session = await session_store.get_session(session_id)
            except SessionStoreUnavailableError as exc:
                await _send_json(
                    websocket,
                    {"type": "error", "code": "session_store", "message": str(exc)},
                )
                await websocket.close(code=1011)
                return
            if session is None:
                await _send_json(
                    websocket,
                    {
                        "type": "error",
                        "code": "not_found",
                        "message": f"Session {session_id} not found.",
                    },
                )
                await websocket.close()
                return

        try:
            session = await session_store.get_or_create_session(session_id)
        except SessionStoreUnavailableError as exc:
            await _send_json(
                websocket,
                {"type": "error", "code": "session_store", "message": str(exc)},
            )
            await websocket.close(code=1011)
            return
    except SessionStoreUnavailableError as exc:
        await _send_json(
            websocket,
            {"type": "error", "code": "session_store", "message": str(exc)},
        )
        await websocket.close(code=1011)
        return

    dg: Optional[DeepgramStreamClient] = None
    _dg_started = False
    timing = TurnTiming()
    stats = DgStats()

    keepalive_stop: Optional[asyncio.Event] = None
    keepalive_task: Optional[asyncio.Task] = None
    last_debug_ts = time.monotonic()
    _voice_active = False  # tracks whether frontend mic is on

    try:
        while True:
            ws_task = asyncio.create_task(websocket.receive())
            dg_task = asyncio.create_task(dg.read_event()) if dg and dg.available else None

            tasks: list[asyncio.Task] = [t for t in (ws_task, dg_task) if t is not None]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            now = time.monotonic()

            if dg_task and dg_task in done:
                await _handle_dg_event(
                    websocket,
                    session,
                    dg_task.result(),
                    session_store,
                    timing,
                    stats,
                )

            if ws_task in done:
                event = ws_task.result()

                if "bytes" in event:
                    chunk = event["bytes"]
                    stats.audio_chunks_received += 1
                    stats.audio_bytes_received += len(chunk)
                    stats.last_audio_chunk_at = now
                    timing.set_first_chunk(now)

                    if stats.audio_chunks_received <= 5:
                        logger.info(
                            "Audio chunk #%d size=%d bytes session=%s",
                            stats.audio_chunks_received,
                            len(chunk),
                            session.session_id,
                        )

                    if len(chunk) == 0:
                        continue

                    if settings.deepgram_api_key and not _dg_started:
                        _dg_started = True
                        dg = _create_deepgram(session.session_id, stats, now)
                        asyncio.create_task(dg.start())
                        keepalive_stop = asyncio.Event()
                        keepalive_task = asyncio.create_task(
                            _keepalive_loop(dg, stats, keepalive_stop)
                        )

                    if dg and not dg.closed:
                        forwarded = await dg.send(chunk)
                        if forwarded:
                            stats.audio_chunks_forwarded += 1
                            stats.audio_bytes_forwarded += len(chunk)
                            if stats.audio_chunks_forwarded <= 5:
                                logger.info(
                                    "Forwarded audio chunk #%d size=%d to Deepgram session=%s",
                                    stats.audio_chunks_forwarded,
                                    len(chunk),
                                    session.session_id,
                                )
                        else:
                            stats.audio_chunks_queued += 1
                            stats.audio_bytes_queued += len(chunk)

                elif "text" in event:
                    try:
                        raw = json.loads(event["text"])
                    except json.JSONDecodeError:
                        await _send_json(
                            websocket,
                            {"type": "error", "code": "bad_json", "message": "Invalid JSON"},
                        )
                        continue

                    msg_type = raw.get("type")

                    if msg_type == "start":
                        await _handle_start(websocket, session, session_store)
                    elif msg_type == "text":
                        text = raw.get("message", "")
                        await _handle_text(websocket, session, text, session_store)
                    elif msg_type == "voice_start":
                        _voice_active = True
                        logger.info("Voice start session=%s", session.session_id)
                        if settings.deepgram_api_key:
                            if dg is None or dg.closed or dg.error:
                                if keepalive_task:
                                    keepalive_task.cancel()
                                    if keepalive_stop:
                                        keepalive_stop.set()
                                if dg:
                                    asyncio.ensure_future(dg.close())
                                _dg_started = True
                                dg = _create_deepgram(session.session_id, stats, now)
                                asyncio.create_task(dg.start())
                                keepalive_stop = asyncio.Event()
                                keepalive_task = asyncio.create_task(
                                    _keepalive_loop(dg, stats, keepalive_stop)
                                )
                                logger.info(
                                    "Deepgram created/restarted session=%s",
                                    session.session_id,
                                )
                            elif not dg.connected and not dg.closed:
                                logger.info(
                                    "Deepgram already connecting session=%s",
                                    session.session_id,
                                )
                    elif msg_type == "voice_stop":
                        _voice_active = False
                        logger.info("Voice stop session=%s", session.session_id)
                        if dg and dg.connected and not dg.closed:
                            await dg.finalize()
                    elif msg_type == "stop":
                        break
                    else:
                        await _send_json(
                            websocket,
                            {"type": "error", "code": "unknown_type", "message": msg_type},
                        )

            for task in pending:
                task.cancel()

            if now - last_debug_ts >= _DEBUG_INTERVAL:
                await _send_audio_debug(websocket, stats)
                last_debug_ts = now

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket handler error")
    finally:
        if keepalive_task:
            keepalive_task.cancel()
            if keepalive_stop:
                keepalive_stop.set()
        if dg:
            await dg.close()
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Deepgram lifecycle helpers
# ---------------------------------------------------------------------------


def _create_deepgram(session_id: str, stats: DgStats, now: float) -> DeepgramStreamClient:
    logger.info("Creating Deepgram client session=%s", session_id)
    dg = DeepgramStreamClient(
        api_key=settings.deepgram_api_key,
        model=settings.deepgram_model,
        language=settings.deepgram_language,
    )
    stats.deepgram_connected_at = now
    return dg


# ---------------------------------------------------------------------------
# Deepgram event handler
# ---------------------------------------------------------------------------


async def _handle_dg_event(
    websocket: WebSocket,
    session: Any,
    event: tuple,
    session_store: SessionStore,
    timing: Optional[TurnTiming] = None,
    stats: Optional[DgStats] = None,
) -> None:
    event_type = event[0]

    if event_type == "connected":
        _, flush_count, flush_bytes = event
        if flush_count > 0:
            logger.info(
                "Deepgram connected — flushed %d queued chunks (%d bytes) session=%s",
                flush_count,
                flush_bytes,
                session.session_id,
            )
        if stats:
            stats.audio_chunks_flushed = flush_count
            stats.audio_bytes_flushed = flush_bytes

    elif event_type == "transcript":
        _, text, is_final = event
        if stats:
            stats.transcript_events_received += 1
            if is_final:
                stats.final_transcripts_received += 1

        if not text.strip():
            logger.debug("Deepgram event ignored — empty text session=%s", session.session_id)
            return

        logger.info(
            "Deepgram event session=%s type=%s text=%r is_final=%s",
            session.session_id,
            event_type,
            text[:200],
            is_final,
        )

        if is_final:
            await _send_json(websocket, {"type": "transcript", "text": text, "is_final": True})
            if timing:
                timing.stt_final_time = time.monotonic()
                timing.start_turn()
            await _handle_text(websocket, session, text, session_store, timing)
        else:
            await _send_json(websocket, {"type": "transcript", "text": text, "is_final": False})

    elif event_type == "error":
        error_msg = event[1] if len(event) > 1 else str(event)
        logger.error(
            "Deepgram event type=error message=%s session=%s",
            error_msg,
            session.session_id,
        )
        await _send_json(
            websocket,
            {
                "type": "error",
                "code": "stt_error",
                "message": "Speech recognition error. Try again or use text.",
            },
        )

    elif event_type == "close":
        code = event[1] if len(event) > 1 else None
        reason = event[2] if len(event) > 2 else ""
        logger.warning(
            "Deepgram closed session=%s code=%s reason=%s",
            session.session_id,
            code,
            reason,
        )
        if stats:
            stats.deepgram_close_code = code
            stats.deepgram_close_reason = reason

        await _send_json(
            websocket,
            {
                "type": "error",
                "code": "deepgram_closed",
                "message": (
                    "Speech recognition disconnected."
                    " Please restart voice capture or use text fallback."
                ),
            },
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _handle_start(
    websocket: WebSocket,
    session: Any,
    session_store: SessionStore,
) -> None:
    """Send the initial greeting prompt for a fresh session."""
    node = NODE_REGISTRY.get(session.current_node.value)
    prompt = node.prompt_template if node else ""

    await _send_json(websocket, {"type": "agent_text", "text": prompt})
    await _send_tts(websocket, prompt, session, session_store)
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
    session_store: SessionStore,
    timing: Optional[TurnTiming] = None,
) -> None:
    if session.call_complete:
        await _send_json(
            websocket, {"type": "error", "message": "This session is already complete."}
        )
        return

    message = message or ""

    if not message.strip() and session.turn_count == 0:
        await _handle_start(websocket, session, session_store)
        return

    session.turn_count += 1

    logger.info(
        "FSM before session=%s node=%s message=%r",
        session.session_id,
        session.current_node.value,
        message[:200],
    )

    if timing:
        timing.fsm_start = time.monotonic()

    result = run_turn(
        current_node_name=session.current_node.value,
        message=message,
        fields=session.extracted_fields,
        retry_count_by_node=session.retry_count_by_node,
        session_id=session.session_id,
        turn_number=session.turn_count,
    )

    if timing:
        timing.fsm_end = time.monotonic()

    logger.info(
        "FSM after  session=%s node=%s->%s assistant=%r",
        session.session_id,
        session.current_node.value,
        result.next_node or "complete",
        result.assistant_message[:200],
    )

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
    try:
        await session_store.update_session(session)
    except SessionStoreUnavailableError as exc:
        await _send_json(websocket, {"type": "error", "code": "session_store", "message": str(exc)})
        await websocket.close(code=1011)
        return

    await _send_json(websocket, {"type": "agent_text", "text": result.assistant_message})

    if timing:
        timing.tts_start = time.monotonic()
    await _send_tts(websocket, result.assistant_message, session, session_store, timing)

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

    # ------------------------------------------------------------------
    # Postgres audit persistence (best-effort, non-blocking)
    # ------------------------------------------------------------------
    await repo.save_session(session)
    await repo.save_transcript(session.session_id, session.turn_count, "user", message)
    await repo.save_transcript(
        session.session_id, session.turn_count, "assistant", result.assistant_message
    )
    if result.guardrail_triggered:
        await repo.save_safety_event(
            session.session_id,
            session.turn_count,
            category=result.guardrail_category or "",
            original_text=result.guardrail_original or "",
            replacement_text=result.assistant_message,
        )
    if result.handoff_triggered and result.red_flag_id:
        await repo.save_escalation_event(
            session.session_id,
            session.turn_count,
            rule_id=result.red_flag_id,
            severity=result.red_flag_severity or "HIGH",
            immediate_handoff=result.red_flag_severity == "CRITICAL",
        )

    if result.call_complete and result.final_summary:
        await repo.save_summary(session.session_id, result.final_summary.model_dump())
        await enrich_summary_with_rag(result.final_summary, result.fields)
        summary_dict = _summary_dict(result.final_summary)
        await _send_json(websocket, {"type": "summary", "summary": summary_dict})
        trace = Trace(
            "summary_complete",
            "chain",
            inputs={"session_id": session.session_id, "node": new_node.value},
        )
        trace.finish(outputs={"summary": summary_dict, "turn_count": session.turn_count})


async def _send_latency(
    websocket: WebSocket,
    session: Any,
    timing: TurnTiming,
    session_store: SessionStore,
) -> None:
    """Record the completed turn and send a latency event to the frontend."""
    client_data = timing.to_client_dict()
    await _send_json(websocket, {"type": "latency", **client_data})
    session.latency_logs.append({"turn_number": timing.turn_counter, **client_data["metrics"]})
    try:
        await session_store.update_session(session)
    except SessionStoreUnavailableError:
        pass
    await repo.save_latency_event(session.session_id, timing.turn_counter, client_data["metrics"])
    trace = Trace(
        "latency_event",
        "tool",
        inputs={"session_id": session.session_id, "turn_id": timing.turn_id},
    )
    trace.finish(outputs={"metrics": client_data["metrics"]})
    timing.reset_utterance()


async def _send_tts(
    websocket: WebSocket,
    text: str,
    session: Any,
    session_store: SessionStore,
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
        await _send_latency(websocket, session, timing, session_store)


async def _send_json(websocket: WebSocket, data: dict[str, Any]) -> None:
    try:
        await websocket.send_json(data)
    except Exception:
        pass


async def _send_audio_debug(websocket: WebSocket, stats: DgStats) -> None:
    await _send_json(
        websocket,
        {
            "type": "audio_debug",
            "chunks_received": stats.audio_chunks_received,
            "bytes_received": stats.audio_bytes_received,
            "chunks_queued": stats.audio_chunks_queued,
            "bytes_queued": stats.audio_bytes_queued,
            "chunks_flushed": stats.audio_chunks_flushed,
            "bytes_flushed": stats.audio_bytes_flushed,
            "chunks_forwarded": stats.audio_chunks_forwarded,
            "bytes_forwarded": stats.audio_bytes_forwarded,
            "transcript_events": stats.transcript_events_received,
            "final_transcripts": stats.final_transcripts_received,
            "keepalives_sent": stats.keepalives_sent,
        },
    )


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
