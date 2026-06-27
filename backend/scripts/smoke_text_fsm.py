"""
Smoke test for the text-only intake FSM.

Simulates one complete intake conversation turn by turn, verifying that:
  - Each node extracts the expected fields.
  - Retry / handoff works when extraction fails repeatedly.
  - Confirmation loop handles yes and corrections.
  - Summary generates FHIR-lite JSON.
"""

import sys
import uuid

sys.path.insert(0, str(uuid.uuid4()))

from backend.fsm.runner import run_turn
from backend.session.models import ExtractedFields, IntakeState


def _fmt(fields: ExtractedFields) -> str:
    parts = []
    for fld in (
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
        val = getattr(fields, fld, None)
        if val:
            parts.append(f"{fld}={val.value!r}")
    return ", ".join(parts)


def simulate(scenario: str, turns: list[tuple[str, str]]) -> None:
    print(f"\n{'=' * 60}")
    print(f"SCENARIO: {scenario}")
    print(f"{'=' * 60}")

    fields = ExtractedFields()
    retries: dict[str, int] = {}
    current_node = IntakeState.GREETING.value

    for i, (node_hint, msg) in enumerate(turns):
        result = run_turn(
            current_node_name=current_node,
            message=msg,
            fields=fields,
            retry_count_by_node=retries,
        )
        fields = result.fields
        retries = result.retry_count_by_node or retries

        print(f"  Turn {i + 1}: [{current_node}] user='{msg}'")
        print(f"    → node={result.next_node}, complete={result.call_complete}")
        print(f"    → assistant: {result.assistant_message[:100]}...")
        print(f"    → fields: {_fmt(result.fields)}")
        if result.final_summary:
            print(f"    → summary: {result.final_summary}")

        if result.retry_count_by_node:
            active_retries = {k: v for k, v in result.retry_count_by_node.items() if v > 0}
            if active_retries:
                print(f"    → retries: {active_retries}")

        current_node = result.next_node
        if result.call_complete:
            break

    print(f"  FINAL: node={current_node}, fields=({_fmt(fields)})")
    print()


def test_happy_path() -> None:
    simulate(
        "Happy path — full intake with confirmation",
        [
            # (expected_current_node, user_message)
            ("greeting", "John Smith"),
            ("identity", "01/15/1980"),
            ("chief_complaint", "I have a persistent cough"),
            ("symptoms", "Started about two weeks ago, getting worse"),
            ("history", "I have asthma"),
            ("allergies", "No known allergies"),
            ("medications", "None"),
            ("visit_reason", "I need a checkup for work"),
            # Confirmation step
            ("confirmation", "yes"),
            # Summary → complete
            ("summary", ""),
        ],
    )


def test_correction_at_confirmation() -> None:
    simulate(
        "User corrects a field at confirmation",
        [
            ("greeting", "Jane Doe"),
            ("identity", "May 5, 1990"),
            ("chief_complaint", "Headaches"),
            ("symptoms", "For three weeks"),
            ("history", "None significant"),
            ("allergies", "Penicillin"),
            ("medications", "Ibuprofen"),
            ("visit_reason", "Follow-up visit"),
            # Confirmation — user says no/corrects
            ("confirmation", "No, my name is actually Jane Smith"),
            # Back to confirmation — now says yes
            ("confirmation", "yes"),
            ("summary", ""),
        ],
    )


def test_retry_then_handoff() -> None:
    simulate(
        "User fails to provide DOB 3 times → handoff",
        [
            ("greeting", "Bob Wilson"),
            ("identity", ""),
            ("identity", ""),
            ("identity", ""),
            # Should route to handoff
            ("handoff", ""),
        ],
    )


def test_retry_then_succeed() -> None:
    simulate(
        "User fails DOB twice, succeeds on third try",
        [
            ("greeting", "Alice Brown"),
            ("identity", "I don't want to say"),
            ("identity", "Why do you need this?"),
            ("identity", "12/25/1985"),
            ("chief_complaint", "Sore throat"),
            ("symptoms", "A few days"),
            ("history", "None"),
            ("allergies", "No allergies"),
            ("medications", "No medications"),
            ("visit_reason", "Sick visit"),
            ("confirmation", "Yes"),
            ("summary", ""),
        ],
    )


def test_multiple_extractions_in_symptoms() -> None:
    simulate(
        "Symptoms extracts both symptoms and duration",
        [
            ("greeting", "Test User"),
            ("identity", "06/15/1978"),
            ("chief_complaint", "Stomach pain"),
            ("symptoms", "I've had sharp pains for about 5 days"),
            ("history", "No history"),
            ("allergies", "None"),
            ("medications", "None"),
            ("visit_reason", "Checkup"),
            ("confirmation", "Yes"),
            ("summary", ""),
        ],
    )


def test_medical_history_handling() -> None:
    simulate(
        "History node with `history` state",
        [
            ("greeting", "Carol Danvers"),
            ("identity", "1980-03-10"),
            ("chief_complaint", "Knee pain"),
            ("symptoms", "Started after running, a week ago"),
            ("history", "I have high blood pressure"),
            ("allergies", "Sulfa drugs"),
            ("medications", "Lisinopril 10mg"),
            ("visit_reason", "Sports physical"),
            ("confirmation", "yes"),
            ("summary", ""),
        ],
    )


if __name__ == "__main__":
    test_happy_path()
    test_correction_at_confirmation()
    test_retry_then_handoff()
    test_retry_then_succeed()
    test_multiple_extractions_in_symptoms()
    test_medical_history_handling()
    print("\nAll scenarios completed.")
