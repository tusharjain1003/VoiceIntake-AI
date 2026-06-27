"""
Smoke test for healthcare safety guardrails.

Tests that:
  - "You may have pneumonia" is blocked (DIAGNOSIS).
  - "You should stop taking that medication" is blocked (MEDICATION_CHANGE).
  - "I've noted that for the care team" is allowed.
  - "Could you tell me when this started?" is allowed.
  - Guardrail integration in the FSM runner replaces unsafe messages.
"""

from backend.fsm.runner import RunResult, _apply_guardrails
from backend.safety.guardrails import check_response_safety


def test_diagnosis_blocked() -> None:
    msg = "You may have pneumonia."
    result = check_response_safety(msg)
    assert not result.safe, "DIAGNOSIS should be blocked"
    assert result.category == "DIAGNOSIS", f"Expected DIAGNOSIS, got {result.category}"
    assert result.replacement is not None, "Should provide a safe replacement"
    print(f"  ✓ DIAGNOSIS blocked:     {msg!r} → {result.category}")


def test_medication_change_blocked() -> None:
    msg = "You should stop taking that medication."
    result = check_response_safety(msg)
    assert not result.safe, "MEDICATION_CHANGE should be blocked"
    assert result.category == "MEDICATION_CHANGE", (
        f"Expected MEDICATION_CHANGE, got {result.category}"
    )
    print(f"  ✓ MEDICATION_CHANGE blocked: {msg!r} → {result.category}")


def test_treatment_recommendation_blocked() -> None:
    msg = "I recommend you start taking an antibiotic."
    result = check_response_safety(msg)
    assert not result.safe, "TREATMENT_RECOMMENDATION should be blocked"
    assert result.category == "TREATMENT_RECOMMENDATION", (
        f"Expected TREATMENT_RECOMMENDATION, got {result.category}"
    )
    print(f"  ✓ TREATMENT_RECOMMENDATION blocked: {msg!r} → {result.category}")


def test_test_result_interpretation_blocked() -> None:
    msg = "Your test results indicate an infection."
    result = check_response_safety(msg)
    assert not result.safe, "TEST_RESULT_INTERPRETATION should be blocked"
    assert result.category == "TEST_RESULT_INTERPRETATION", (
        f"Expected TEST_RESULT_INTERPRETATION, got {result.category}"
    )
    print(f"  ✓ TEST_RESULT_INTERPRETATION blocked: {msg!r} → {result.category}")


def test_urgency_claim_blocked() -> None:
    msg = "You're fine, don't worry about it."
    result = check_response_safety(msg)
    assert not result.safe, "URGENCY_CLAIM should be blocked"
    assert result.category == "URGENCY_CLAIM_TO_PATIENT", (
        f"Expected URGENCY_CLAIM_TO_PATIENT, got {result.category}"
    )
    print(f"  ✓ URGENCY_CLAIM blocked:    {msg!r} → {result.category}")


def test_reassurance_dismissal_blocked() -> None:
    msg = "That's normal, it's probably nothing."
    result = check_response_safety(msg)
    assert not result.safe, "REASSURANCE_OR_DISMISSAL should be blocked"
    assert result.category == "REASSURANCE_OR_DISMISSAL", (
        f"Expected REASSURANCE_OR_DISMISSAL, got {result.category}"
    )
    print(f"  ✓ REASSURANCE_OR_DISMISSAL blocked: {msg!r} → {result.category}")


def test_neutral_intake_allowed() -> None:
    allowed = [
        (
            "I've noted that for the care team. "
            "Could you tell me a little more about when this started?"
        ),
        "Could you tell me when this started?",
        "Thank you. Please tell me your full name and date of birth.",
        "What brings you in today?",
        "Here is what I have recorded:\n  Patient Name: John Smith",
        "Thank you. Your intake is complete. A clinician will review your information shortly.",
        "I didn't quite get that. Could you please provide your date of birth?",
        "Do you have any allergies to medications, foods, or anything else?",
    ]
    for msg in allowed:
        result = check_response_safety(msg)
        assert result.safe, f"Should be allowed but was blocked: {msg!r} → {result.category}"
    print(f"  ✓ {len(allowed)} neutral messages allowed")


def test_integration_replaces_unsafe() -> None:
    """Verify that _apply_guardrails replaces unsafe assistant_message."""
    result = RunResult(
        next_node="complete",
        assistant_message="You may have pneumonia.",
        fields=None,  # type: ignore
        call_complete=True,
    )
    guarded = _apply_guardrails(result)
    assert guarded.assistant_message != "You may have pneumonia.", (
        "Guardrail should have replaced the message"
    )
    assert "noted that for the care team" in guarded.assistant_message, (
        "Should contain the safe replacement text"
    )
    print("  ✓ Integration replacement: unsafe → safe")


def test_integration_passes_safe() -> None:
    """Verify that _apply_guardrails leaves safe messages unchanged."""
    msg = "What brings you in today?"
    result = RunResult(
        next_node="chief_complaint",
        assistant_message=msg,
        fields=None,  # type: ignore
        call_complete=False,
    )
    guarded = _apply_guardrails(result)
    assert guarded.assistant_message == msg, "Safe message should pass through unchanged"
    print("  ✓ Integration pass-through: safe message unchanged")


if __name__ == "__main__":
    print("Guardrail classification tests:\n")
    test_diagnosis_blocked()
    test_medication_change_blocked()
    test_treatment_recommendation_blocked()
    test_test_result_interpretation_blocked()
    test_urgency_claim_blocked()
    test_reassurance_dismissal_blocked()
    test_neutral_intake_allowed()

    print("\nFSM runner integration tests:\n")
    test_integration_replaces_unsafe()
    test_integration_passes_safe()

    print("\nAll guardrail tests passed.")
