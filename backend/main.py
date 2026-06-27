from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.fsm.runner import run_turn
from backend.session.manager import session_manager
from backend.session.models import (
    IntakeState,
    TextIntakeRequest,
    TextIntakeResponse,
)

app = FastAPI(title="VoiceIntake AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/text/intake/{session_id}", response_model=TextIntakeResponse)
def text_intake(session_id: str, body: TextIntakeRequest) -> TextIntakeResponse:
    if session_id == "new":
        session_id = session_manager.create_session()
    session = session_manager.get_or_create_session(session_id)

    if session.call_complete:
        return TextIntakeResponse(
            session_id=session.session_id,
            assistant_message="This session is already complete.",
            current_node=IntakeState.COMPLETE,
            extracted_fields=session.extracted_fields,
            call_complete=True,
        )

    message = body.message or ""

    # First message with no user input yet — return the greeting prompt.
    if not message.strip() and session.turn_count == 0:
        from backend.fsm.nodes import NODE_REGISTRY

        node = NODE_REGISTRY.get(session.current_node.value)
        prompt = node.prompt_template if node else ""
        return TextIntakeResponse(
            session_id=session.session_id,
            assistant_message=prompt,
            current_node=session.current_node,
            extracted_fields=session.extracted_fields,
            call_complete=False,
        )

    session.turn_count += 1
    result = run_turn(
        current_node_name=session.current_node.value,
        message=message,
        fields=session.extracted_fields,
    )

    new_node = IntakeState(result.next_node) if result.next_node else IntakeState.COMPLETE
    session.current_node = new_node
    session.extracted_fields = result.fields
    session.call_complete = result.call_complete
    session_manager.update_session(session)

    return TextIntakeResponse(
        session_id=session.session_id,
        assistant_message=result.assistant_message,
        current_node=new_node,
        extracted_fields=result.fields,
        call_complete=result.call_complete,
        final_summary=result.final_summary,
    )
