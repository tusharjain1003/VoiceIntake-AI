import logging

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.runner import run_turn
from backend.rag.enrich import enrich_summary_with_rag
from backend.session import manager as session_mgr
from backend.session.exceptions import SessionStoreUnavailableError
from backend.session.models import IntakeState, TextIntakeResponse
from backend.tracing.langsmith import Trace

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceIntake AI", version="0.1.0")

origins = settings.cors_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=bool(origins) and origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    from backend.database import AsyncSessionLocal, create_engine, init_redis
    from backend.db import repository as repo
    from backend.db.migrate import run_migrations

    try:
        create_engine()
        from backend.database import async_engine

        if async_engine is not None:
            await run_migrations(async_engine)
            logger.info("Database migrations applied")
        if AsyncSessionLocal is not None:
            repo.init_repository(AsyncSessionLocal)
            logger.info("Postgres repository initialised")
    except Exception as exc:
        logger.warning("Postgres unavailable — DB persistence disabled: %s", exc)

    try:
        await init_redis()
    except Exception as exc:
        logger.warning("Redis unavailable — session persistence disabled: %s", exc)

    try:
        await session_mgr.init_session_manager()
    except SessionStoreUnavailableError as exc:
        logger.critical("Session store unavailable: %s", exc)
        raise

    logger.info("CORS allowed origins: %s", origins)


@app.on_event("shutdown")
async def shutdown() -> None:
    from backend.database import close_engine, close_redis

    await close_redis()
    await close_engine()
    logger.info("Shutdown complete")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    from backend.database import async_engine
    from backend.database import redis_client as db_redis
    from backend.db import repository as repo

    db_avail = async_engine is not None and repo.is_available()
    redis_avail = db_redis is not None
    if db_avail and redis_avail:
        status = "ok"
    elif db_avail or redis_avail:
        status = "degraded"
    else:
        status = "unavailable"
    return {
        "status": status,
        "db_available": db_avail,
        "redis_available": redis_avail,
    }


@app.get("/api/sessions")
async def list_sessions() -> dict:
    from backend.session.models import SessionData

    if session_mgr.session_manager is None:
        raise HTTPException(status_code=503, detail="Session store not initialized.")
    try:
        keys = await session_mgr.session_manager.redis.keys("session:*")
        sessions = []
        for key in keys[-20:]:
            raw = await session_mgr.session_manager.redis.get(key)
            if raw:
                try:
                    s = SessionData.model_validate_json(raw)
                    sessions.append(
                        {
                            "session_id": s.session_id,
                            "current_node": s.current_node.value if s.current_node else None,
                            "call_complete": s.call_complete,
                            "turn_count": s.turn_count,
                            "handoff_triggered": s.handoff_triggered,
                        }
                    )
                except Exception:
                    pass
        return {"sessions": list(reversed(sessions))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/text/intake/{session_id}")
async def text_intake(session_id: str, body: dict) -> dict:
    if session_mgr.session_manager is None:
        raise HTTPException(status_code=503, detail="Session store not initialized.")

    try:
        if session_id == "new":
            session_id = await session_mgr.session_manager.create_session()
        session = await session_mgr.session_manager.get_or_create_session(session_id)
    except SessionStoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if session.call_complete:
        return TextIntakeResponse(
            session_id=session.session_id,
            assistant_message="This session is already complete.",
            current_node=IntakeState.COMPLETE,
            extracted_fields=session.extracted_fields,
            call_complete=True,
        ).model_dump()

    message = (body or {}).get("message", "")

    if not message.strip() and session.turn_count == 0:
        node = NODE_REGISTRY.get(session.current_node.value)
        prompt = node.prompt_template if node else ""
        return TextIntakeResponse(
            session_id=session.session_id,
            assistant_message=prompt,
            current_node=session.current_node,
            extracted_fields=session.extracted_fields,
            call_complete=False,
        ).model_dump()

    session.turn_count += 1
    result = run_turn(
        current_node_name=session.current_node.value,
        message=message,
        fields=session.extracted_fields,
        retry_count_by_node=session.retry_count_by_node,
        session_id=session.session_id,
        turn_number=session.turn_count,
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
        await session_mgr.session_manager.update_session(session)
    except SessionStoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # ------------------------------------------------------------------
    # Postgres audit persistence (best-effort, non-blocking)
    # ------------------------------------------------------------------
    from backend.db import repository as repo

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
        trace = Trace(
            "summary_complete",
            "chain",
            inputs={"session_id": session.session_id, "node": new_node.value},
        )
        trace.finish(
            outputs={
                "summary": result.final_summary.model_dump(),
                "turn_count": session.turn_count,
            }
        )

    return TextIntakeResponse(
        session_id=session.session_id,
        assistant_message=result.assistant_message,
        current_node=new_node,
        extracted_fields=result.fields,
        call_complete=result.call_complete,
        final_summary=result.final_summary,
        handoff_triggered=result.handoff_triggered,
        red_flag_severity=result.red_flag_severity,
        red_flag_id=result.red_flag_id,
        handoff_reason=result.handoff_reason,
    ).model_dump()


@app.websocket("/ws/intake/{session_id}")
async def ws_intake(websocket: WebSocket, session_id: str) -> None:
    if session_mgr.session_manager is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Session store not initialized."})
        await websocket.close(code=1011)
        return

    from backend.ws.handler import handle_intake_ws

    await handle_intake_ws(websocket, session_id, session_mgr.session_manager)
