"""
Smoke test for red-flag escalation.

Tests that:
  - Chest pain triggers a HIGH flag (no immediate handoff).
  - Suicidal ideation triggers a CRITICAL flag (immediate handoff).
  - Neutral messages trigger no escalation.
  - FSM runner integration: CRITICAL flag routes to handoff with specific message.
  - FSM runner integration: HIGH flag continues intake with red_flag fields set.
"""

from backend.fsm.runner import RunResult, _check_and_apply_escalation
from backend.safety.escalation import check_escalation
from backend.session.models import ExtractedFields


def test_chest_pain_high() -> None:
    msg = "I've been having chest pain for the past few days."
    result = check_escalation(msg)
    assert result is not None, "Chest pain should trigger escalation"
    assert result.flag_id == "CHEST_PAIN_DYSPNEA", (
        f"Expected CHEST_PAIN_DYSPNEA, got {result.flag_id}"
    )
    assert result.severity == "HIGH", f"Expected HIGH, got {result.severity}"
    assert result.immediate_handoff is False, "CHEST_PAIN should not be immediate handoff"
    print(f"  ✓ CHEST_PAIN → severity={result.severity}, handoff={result.immediate_handoff}")


def test_suicidal_ideation_critical() -> None:
    msg = "I want to kill myself."
    result = check_escalation(msg)
    assert result is not None, "Suicidal ideation should trigger escalation"
    assert result.flag_id == "SUICIDAL_IDEATION", (
        f"Expected SUICIDAL_IDEATION, got {result.flag_id}"
    )
    assert result.severity == "CRITICAL", f"Expected CRITICAL, got {result.severity}"
    assert result.immediate_handoff is True, "SUICIDAL_IDEATION should trigger immediate handoff"
    print(f"  ✓ SUICIDAL_IDEATION → severity={result.severity}, handoff={result.immediate_handoff}")


def test_neutral_no_escalation() -> None:
    neutral = [
        "My name is John.",
        "I was born on 01/15/1980.",
        "No allergies that I know of.",
        "I don't take any medications.",
        "Yes, that looks correct.",
        "Thank you.",
    ]
    for msg in neutral:
        result = check_escalation(msg)
        assert result is None, f"Neutral message should not escalate: {msg!r}"
    print(f"  ✓ {len(neutral)} neutral messages — no escalation")


def test_shortness_of_breath_high() -> None:
    msg = "I've been short of breath lately."
    result = check_escalation(msg)
    assert result is not None, "Shortness of breath should trigger escalation"
    assert result.severity == "HIGH", f"Expected HIGH, got {result.severity}"
    print(f"  ✓ SHORTNESS_OF_BREATH → severity={result.severity}")


def test_severe_breathing_difficulty_critical() -> None:
    msg = "I can't catch my breath."
    result = check_escalation(msg)
    assert result is not None, "Severe breathing difficulty should trigger escalation"
    assert result.flag_id == "SEVERE_BREATHING_DIFFICULTY", (
        f"Expected SEVERE_BREATHING_DIFFICULTY, got {result.flag_id}"
    )
    assert result.severity == "CRITICAL", f"Expected CRITICAL, got {result.severity}"
    assert result.immediate_handoff is True
    print(f"  ✓ SEVERE_BREATHING_DIFFICULTY → severity={result.severity}")


def test_integration_critical_handoff() -> None:
    """CRITICAL flag in runner overrides next_node and message."""
    result = RunResult(
        next_node="symptoms",
        assistant_message="Can you tell me more?",
        fields=ExtractedFields(),
        call_complete=False,
    )
    guarded = _check_and_apply_escalation(result, "I want to kill myself.")
    assert guarded.handoff_triggered is True, "Should mark handoff_triggered"
    assert guarded.red_flag_severity == "CRITICAL"
    assert guarded.red_flag_id == "SUICIDAL_IDEATION"
    assert guarded.next_node == "handoff", f"Should route to handoff, got {guarded.next_node}"
    assert "pause the intake" in guarded.assistant_message
    assert "emergency" in guarded.assistant_message
    print("  ✓ CRITICAL integration → handoff message set")


def test_integration_high_continues() -> None:
    """HIGH flag sets metadata but continues intake."""
    result = RunResult(
        next_node="history",
        assistant_message="Do you have any medical history?",
        fields=ExtractedFields(),
        call_complete=False,
    )
    guarded = _check_and_apply_escalation(result, "I've been having chest pain.")
    assert guarded.handoff_triggered is True, "Should mark handoff_triggered"
    assert guarded.red_flag_severity == "HIGH"
    assert guarded.red_flag_id == "CHEST_PAIN_DYSPNEA"
    assert guarded.next_node == "history", "HIGH should not change next_node"
    assert guarded.assistant_message == "Do you have any medical history?"
    print("  ✓ HIGH integration → next_node unchanged")


if __name__ == "__main__":
    print("Escalation classification tests:\n")
    test_chest_pain_high()
    test_suicidal_ideation_critical()
    test_shortness_of_breath_high()
    test_severe_breathing_difficulty_critical()
    test_neutral_no_escalation()

    print("\nFSM runner integration tests:\n")
    test_integration_critical_handoff()
    test_integration_high_continues()

    print("\nAll escalation tests passed.")
