import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.runner import run_turn
from backend.session.manager import session_manager
from backend.session.models import IntakeState, TextIntakeResponse

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceIntake AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    from backend.database import create_engine, init_redis
    from backend.db.migrate import run_migrations

    try:
        create_engine()
        from backend.database import async_engine

        if async_engine is not None:
            await run_migrations(async_engine)
            logger.info("Database migrations applied")
    except Exception as exc:
        logger.warning("Postgres unavailable — DB persistence disabled: %s", exc)

    try:
        await init_redis()
    except Exception as exc:
        logger.warning("Redis unavailable — session persistence disabled: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    from backend.database import close_engine, close_redis

    await close_redis()
    await close_engine()
    logger.info("Shutdown complete")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/text/intake/{session_id}")
async def text_intake(session_id: str, body: dict) -> dict:
    if session_id == "new":
        session_id = await session_manager.create_session()
    session = await session_manager.get_or_create_session(session_id)

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
    await session_manager.update_session(session)

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
    from backend.ws.handler import handle_intake_ws

    await handle_intake_ws(websocket, session_id)
