import uuid
from dataclasses import dataclass
from typing import Optional

from backend.fsm.nodes import NODE_REGISTRY
from backend.observability.latency_tracker import LatencyTracker
from backend.session.models import (
    ExtractedFields,
    FieldValue,
    IntakeState,
    PreVisitSummary,
)


@dataclass
class RunResult:
    next_node: Optional[str]
    assistant_message: str
    fields: ExtractedFields
    call_complete: bool
    final_summary: Optional[PreVisitSummary] = None


def _build_summary(fields: ExtractedFields) -> PreVisitSummary:
    return PreVisitSummary(
        patient_name=fields.patient_name.value if fields.patient_name else None,
        date_of_birth=fields.date_of_birth.value if fields.date_of_birth else None,
        chief_complaint=fields.chief_complaint.value if fields.chief_complaint else None,
        symptoms=fields.symptoms.value if fields.symptoms else None,
        medical_history=fields.medical_history.value if fields.medical_history else None,
        allergies=fields.allergies.value if fields.allergies else None,
        medications=fields.medications.value if fields.medications else None,
        visit_reason=fields.visit_reason.value if fields.visit_reason else None,
    )


def run_turn(
    current_node_name: str,
    message: str,
    fields: Optional[ExtractedFields] = None,
) -> RunResult:
    tracker = LatencyTracker()
    tracker.start("run_turn")

    if fields is None:
        fields = ExtractedFields()

    node = NODE_REGISTRY.get(current_node_name)
    if node is None:
        return RunResult(
            next_node=None,
            assistant_message="I'm sorry, something went wrong.",
            fields=fields,
            call_complete=True,
        )

    turn_id = str(uuid.uuid4())

    if message.strip() and node.extract_field:
        setattr(
            fields,
            node.extract_field,
            FieldValue(
                value=message.strip(),
                confidence=0.8,
                source_turn_id=turn_id,
                confirmed=False,
            ),
        )

    if not node.transitions:
        summary = _build_summary(fields)
        tracker.stop("run_turn")
        return RunResult(
            next_node=IntakeState.COMPLETE.value,
            assistant_message=(
                "Thank you. Your intake is complete. "
                "A clinician will review your information shortly."
            ),
            fields=fields,
            call_complete=True,
            final_summary=summary,
        )

    next_node_name = node.transitions[0]
    next_node = NODE_REGISTRY.get(next_node_name)
    assistant_message = next_node.prompt_template if next_node else ""

    call_complete = next_node_name == IntakeState.COMPLETE.value
    final_summary = None

    if call_complete:
        final_summary = _build_summary(fields)
        assistant_message = (
            "Thank you. Your intake is complete. "
            "A clinician will review your information shortly.\n\n"
            f"Here is a summary of your intake:\n{final_summary.model_dump_json(indent=2)}"
        )
    elif next_node_name == IntakeState.SUMMARY.value:
        summary = _build_summary(fields)
        summary_lines = ["Here is what I have recorded:"]
        field_labels = {
            "patient_name": "Patient Name",
            "date_of_birth": "Date of Birth",
            "chief_complaint": "Chief Complaint",
            "symptoms": "Symptoms",
            "medical_history": "Medical History",
            "allergies": "Allergies",
            "medications": "Medications",
            "visit_reason": "Visit Reason",
        }
        for field, label in field_labels.items():
            value = getattr(summary, field, None)
            if value:
                summary_lines.append(f"- {label}: {value}")
        summary_lines.append("")
        summary_lines.append(assistant_message)
        assistant_message = "\n".join(summary_lines)

    tracker.stop("run_turn")
    return RunResult(
        next_node=next_node_name,
        assistant_message=assistant_message,
        fields=fields,
        call_complete=call_complete,
        final_summary=final_summary,
    )
