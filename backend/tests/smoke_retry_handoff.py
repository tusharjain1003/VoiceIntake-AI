"""
Smoke test: retry exhaustion immediately completes with a handoff.

This exercises the FSM directly so REST and WebSocket callers inherit the same
terminal handoff behavior through ``RunResult``.
"""

from backend.fsm.runner import MAX_RETRIES_PER_NODE, run_turn
from backend.session.models import ExtractedFields, IntakeState


def test_retry_exhaustion_handoff_completes() -> None:
    fields = ExtractedFields()
    retries: dict[str, int] = {}

    result = None
    for _ in range(MAX_RETRIES_PER_NODE):
        result = run_turn(
            current_node_name=IntakeState.IDENTITY.value,
            message="",
            fields=fields,
            retry_count_by_node=retries,
        )
        fields = result.fields
        retries = result.retry_count_by_node or retries

    assert result is not None
    assert result.next_node == IntakeState.HANDOFF.value
    assert result.call_complete is True
    assert result.handoff_triggered is True
    assert result.handoff_reason == (
        "Could not collect required intake information after multiple attempts."
    )
    assert result.final_summary is not None
    assert retries[IntakeState.IDENTITY.value] == MAX_RETRIES_PER_NODE


if __name__ == "__main__":
    test_retry_exhaustion_handoff_completes()
    print("Retry exhaustion handoff smoke check passed.")
