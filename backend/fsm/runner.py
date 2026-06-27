import json
import re
import uuid
from dataclasses import dataclass
from typing import Optional

from backend.fsm.nodes import NODE_REGISTRY
from backend.fsm.prompts import PROMPTS
from backend.observability.latency_tracker import LatencyTracker
from backend.safety.escalation import check_escalation
from backend.safety.guardrails import check_response_safety
from backend.session.models import (
    ExtractedFields,
    FieldValue,
    IntakeState,
    PreVisitSummary,
)

MAX_RETRIES_PER_NODE = 3

_CRITICAL_HANDOFF_MSG = (
    "I'm going to pause the intake and connect you with a human team member now. "
    "If you feel you may be in immediate danger or this is an emergency, "
    "please contact local emergency services right away."
)


@dataclass
class RunResult:
    next_node: Optional[str]
    assistant_message: str
    fields: ExtractedFields
    call_complete: bool
    final_summary: Optional[PreVisitSummary] = None
    retry_count_by_node: Optional[dict[str, int]] = None
    handoff_triggered: bool = False
    red_flag_severity: Optional[str] = None
    red_flag_id: Optional[str] = None
    handoff_reason: Optional[str] = None


def _apply_guardrails(result: RunResult) -> RunResult:
    """Replace *assistant_message* with a safe neutral response if the
    guardrail classifier flags it."""
    if result.assistant_message:
        gr = check_response_safety(result.assistant_message)
        if not gr.safe and gr.replacement is not None:
            result.assistant_message = gr.replacement
    return result


# ---------------------------------------------------------------------------
# Field label mapping (for display in confirmation)
# ---------------------------------------------------------------------------
_FIELD_LABELS: dict[str, str] = {
    "patient_name": "Patient Name",
    "date_of_birth": "Date of Birth",
    "chief_complaint": "Chief Complaint",
    "symptoms": "Symptoms",
    "symptom_duration": "Symptom Duration",
    "medical_history": "Medical History",
    "allergies": "Allergies",
    "medications": "Medications",
    "visit_reason": "Visit Reason",
}


def _build_summary(fields: ExtractedFields) -> PreVisitSummary:
    return PreVisitSummary(
        patient_name=fields.patient_name.value if fields.patient_name else None,
        date_of_birth=fields.date_of_birth.value if fields.date_of_birth else None,
        chief_complaint=fields.chief_complaint.value if fields.chief_complaint else None,
        symptoms=fields.symptoms.value if fields.symptoms else None,
        symptom_duration=fields.symptom_duration.value if fields.symptom_duration else None,
        medical_history=fields.medical_history.value if fields.medical_history else None,
        allergies=fields.allergies.value if fields.allergies else None,
        medications=fields.medications.value if fields.medications else None,
        visit_reason=fields.visit_reason.value if fields.visit_reason else None,
    )


def _get_field_value(fields: ExtractedFields, field_name: str) -> Optional[str]:
    return getattr(getattr(fields, field_name, None), "value", None)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------
_NAME_PATTERNS = [
    re.compile(r"my name is (.+?)(?: and|\.|$)", re.IGNORECASE),
    re.compile(r"i'?m (.+?)(?: and|\.|$| my)", re.IGNORECASE),
    re.compile(r"i am (.+?)(?: and|\.|$)", re.IGNORECASE),
    re.compile(r"call me (.+?)(?: and|\.|$)", re.IGNORECASE),
]

_DOB_PATTERNS = [
    re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"),
    re.compile(
        r"(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+\d{1,2},?\s+\d{4}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december),?\s+\d{4}",
        re.IGNORECASE,
    ),
    re.compile(r"\d{4}[/-]\d{2}[/-]\d{2}"),
    re.compile(r"born (?:on )?(.+?)(?: and|\.|$)", re.IGNORECASE),
]

_DURATION_PATTERNS = [
    re.compile(r"(\d+\s*(?:day|days|week|weeks|month|months|year|years))", re.IGNORECASE),
    re.compile(
        r"((?:a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|days|week|weeks|month|months|year|years))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:for|about|around)\s+(\d+\s*(?:day|days|week|weeks|month|months|year|years))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:last(?:ed|ing)?)\s+(\d+\s*(?:day|days|week|weeks|month|months|year|years))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:started|began)\s+(\d+\s*(?:day|days|week|weeks|month|months|year|years)\s+ago)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:started|began)\s+((?:a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:day|days|week|weeks|month|months|year|years)\s+ago)",
        re.IGNORECASE,
    ),
]

_AFFIRMATIVE = re.compile(
    r"^(?:yes|ye[ahp]|correct|right|looks?\s+good|that'?s?\s+(?:right|correct)|good|fine|ok(?:ay)?)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"^(?:no|nope|wrong|incorrect|not\s+right|not\s+correct|that'?s?\s+not)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Per-node extraction functions
# ---------------------------------------------------------------------------
def _extract_for_greeting(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    name = None
    for pat in _NAME_PATTERNS:
        m = pat.search(message)
        if m:
            name = m.group(1).strip()
            break
    if not name:
        words = message.strip().split()
        if len(words) >= 2:
            name = message.strip()
    if name:
        fields.patient_name = FieldValue(
            value=name, confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
        return fields, True
    return fields, bool(message.strip())


def _extract_for_identity(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    for pat in _DOB_PATTERNS:
        m = pat.search(message)
        if m:
            fields.date_of_birth = FieldValue(
                value=m.group(0).strip(), confidence=0.8, source_turn_id=turn_id, confirmed=False
            )
            break
    if fields.date_of_birth is not None:
        return fields, True
    if not fields.patient_name:
        name = None
        for pat in _NAME_PATTERNS:
            m = pat.search(message)
            if m:
                name = m.group(1).strip()
                break
        if not name and len(message.strip().split()) >= 2:
            name = message.strip()
        if name:
            fields.patient_name = FieldValue(
                value=name, confidence=0.8, source_turn_id=turn_id, confirmed=False
            )
            return fields, True
    return fields, False


def _extract_for_chief_complaint(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    if message.strip():
        fields.chief_complaint = FieldValue(
            value=message.strip(), confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
        return fields, True
    return fields, False


def _extract_for_symptoms(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    if not message.strip():
        return fields, False
    fields.symptoms = FieldValue(
        value=message.strip(), confidence=0.8, source_turn_id=turn_id, confirmed=False
    )
    for pat in _DURATION_PATTERNS:
        m = pat.search(message)
        if m:
            fields.symptom_duration = FieldValue(
                value=m.group(1).strip(), confidence=0.7, source_turn_id=turn_id, confirmed=False
            )
            break
    return fields, True


def _extract_for_history(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    if message.strip():
        fields.medical_history = FieldValue(
            value=message.strip(), confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
        return fields, True
    return fields, False


def _extract_for_allergies(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    text = message.strip()
    if not text:
        return fields, False
    if re.search(r"\bno\s+(?:known\s+)?allerg(?:ies|y)", text, re.IGNORECASE) or re.search(
        r"\bnone\b", text, re.IGNORECASE
    ):
        fields.allergies = FieldValue(
            value="No known allergies", confidence=0.9, source_turn_id=turn_id, confirmed=False
        )
    else:
        fields.allergies = FieldValue(
            value=text, confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
    return fields, True


def _extract_for_medications(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    text = message.strip()
    if not text:
        return fields, False
    if re.search(
        r"\bno\s+(?:medications?|meds|medicine|prescriptions?)\b", text, re.IGNORECASE
    ) or re.search(r"\b(?:not\s+)?none\b", text, re.IGNORECASE):
        fields.medications = FieldValue(
            value="No current medications", confidence=0.9, source_turn_id=turn_id, confirmed=False
        )
    else:
        fields.medications = FieldValue(
            value=text, confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
    return fields, True


def _extract_for_visit_reason(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, bool]:
    if message.strip():
        fields.visit_reason = FieldValue(
            value=message.strip(), confidence=0.8, source_turn_id=turn_id, confirmed=False
        )
        return fields, True
    return fields, False


def _correction_field_name(text: str) -> Optional[str]:
    mapping = [
        (r"\bname\b", "patient_name"),
        (r"\bdob\b|\bdate\s+of\s+birth\b|\bbirth\b|\bborn\b", "date_of_birth"),
        (
            r"\b(?:chief\s+)?complaint\b|\bmain\s+concern\b|\b(?:reason|issue|problem)\b",
            "chief_complaint",
        ),
        (r"\bsymptom\b|\bduration\b|\bwhen\b", "symptoms"),
        (r"\bhistory\b|\bmedical\b|\bcondition\b", "medical_history"),
        (r"\ballerg\b", "allergies"),
        (r"\bmedication\b|\bmeds\b|\bmedicine\b|\btaking\b", "medications"),
        (r"\bvisit\b|\bappointment\b|\breason\b", "visit_reason"),
    ]
    for pat, field in mapping:
        if re.search(pat, text, re.IGNORECASE):
            return field
    return None


def _extract_correction_value(text: str) -> str:
    for prefix in [
        r"it'?s?\s+",
        r"it\s+should\s+be\s+",
        r"(?:my|the)\s+\w[\w\s]+\s+(?:is|are)\s+",
        r"(?:i\s+)?meant\s+",
        r"(?:i\s+)?said\s+",
    ]:
        m = re.search(prefix, text, re.IGNORECASE)
        if m:
            val = text[m.end() :].strip().strip(".,!?")
            if val:
                val = re.sub(
                    r"^(?:actually|rather|just|simply|probably)\s+", "", val, flags=re.IGNORECASE
                ).strip()
                if val:
                    return val
    val = text.strip().strip(".,!?")
    val = re.sub(
        r"^(?:actually|rather|just|simply|probably)\s+", "", val, flags=re.IGNORECASE
    ).strip()
    return val


def _extract_for_confirmation(
    message: str, fields: ExtractedFields, turn_id: str
) -> tuple[ExtractedFields, str, bool]:
    text = message.strip()
    if not text:
        return fields, "retry", False

    if _AFFIRMATIVE.search(text):
        return fields, "summary", True

    if _NEGATIVE.search(text) or any(
        w in text.lower()
        for w in ["wrong", "incorrect", "fix", "change", "update", "actually", "meant", "correct"]
    ):
        correction_field = _correction_field_name(text)
        if correction_field:
            val = _extract_correction_value(text)
            if val and val.lower() not in (
                "no",
                "nope",
                "wrong",
                "incorrect",
                "fix",
                "change",
                "update",
            ):
                setattr(
                    fields,
                    correction_field,
                    FieldValue(value=val, confidence=0.8, source_turn_id=turn_id, confirmed=False),
                )
                return fields, "confirmation", True
        return fields, "retry", False

    if any(
        w in text.lower()
        for w in [
            "name",
            "dob",
            "date",
            "birth",
            "allerg",
            "medication",
            "symptom",
            "history",
            "complaint",
            "visit",
        ]
    ):
        correction_field = _correction_field_name(text)
        if correction_field:
            val = _extract_correction_value(text)
            if val:
                setattr(
                    fields,
                    correction_field,
                    FieldValue(value=val, confidence=0.8, source_turn_id=turn_id, confirmed=False),
                )
                return fields, "confirmation", True
        return fields, "retry", False

    return fields, "retry", False


# ---------------------------------------------------------------------------
# FHIR-lite summary
# ---------------------------------------------------------------------------
def _build_fhir_json(fields: ExtractedFields) -> str:
    summary = _build_summary(fields)
    entry = []
    if summary.patient_name:
        entry.append(
            {
                "resource": {
                    "resourceType": "Patient",
                    "name": [{"text": summary.patient_name}],
                    "birthDate": summary.date_of_birth or "",
                }
            }
        )
    if summary.chief_complaint:
        entry.append(
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "preliminary",
                    "code": {"text": "Chief Complaint"},
                    "valueString": summary.chief_complaint,
                }
            }
        )
    if summary.symptom_duration or summary.symptoms:
        entry.append(
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "preliminary",
                    "code": {"text": "Symptom Details"},
                    "valueString": (
                        f"Symptoms: {summary.symptoms or 'N/A'}. "
                        f"Duration: {summary.symptom_duration or 'N/A'}"
                    ),
                }
            }
        )
    if summary.medical_history:
        entry.append(
            {
                "resource": {
                    "resourceType": "Condition",
                    "clinicalStatus": {"text": "active"},
                    "code": {"text": summary.medical_history},
                }
            }
        )
    if summary.allergies:
        entry.append(
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "code": {"text": summary.allergies},
                }
            }
        )
    if summary.medications:
        entry.append(
            {
                "resource": {
                    "resourceType": "MedicationStatement",
                    "status": "active",
                    "medicationCodeableConcept": {"text": summary.medications},
                }
            }
        )
    if summary.visit_reason:
        entry.append(
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "preliminary",
                    "code": {"text": "Visit Reason"},
                    "valueString": summary.visit_reason,
                }
            }
        )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entry,
    }
    return json.dumps(bundle, indent=2)


# ---------------------------------------------------------------------------
# Build confirmation display text
# ---------------------------------------------------------------------------
def _build_confirmation_text(fields: ExtractedFields) -> str:
    lines = ["Here is what I have recorded:"]
    for field_name, label in _FIELD_LABELS.items():
        val = _get_field_value(fields, field_name)
        lines.append(f"  {label}: {val or '[not provided]'}")
    lines.append("")
    lines.append(PROMPTS["confirmation"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
_EXTRACTORS: dict[str, callable] = {
    IntakeState.GREETING.value: _extract_for_greeting,
    IntakeState.IDENTITY.value: _extract_for_identity,
    IntakeState.CHIEF_COMPLAINT.value: _extract_for_chief_complaint,
    IntakeState.SYMPTOMS.value: _extract_for_symptoms,
    IntakeState.HISTORY.value: _extract_for_history,
    IntakeState.ALLERGIES.value: _extract_for_allergies,
    IntakeState.MEDICATIONS.value: _extract_for_medications,
    IntakeState.VISIT_REASON.value: _extract_for_visit_reason,
}


def run_turn(
    current_node_name: str,
    message: str,
    fields: Optional[ExtractedFields] = None,
    retry_count_by_node: Optional[dict[str, int]] = None,
) -> RunResult:
    tracker = LatencyTracker()
    tracker.start("run_turn")

    if fields is None:
        fields = ExtractedFields()
    if retry_count_by_node is None:
        retry_count_by_node = {}

    node = NODE_REGISTRY.get(current_node_name)
    if node is None:
        return _apply_guardrails(
            RunResult(
                next_node=None,
                assistant_message="I'm sorry, something went wrong.",
                fields=fields,
                call_complete=True,
            )
        )

    turn_id = str(uuid.uuid4())

    # Handle special nodes: CONFIRMATION, SUMMARY, HANDOFF
    if current_node_name == IntakeState.CONFIRMATION.value:
        result_fields, action, success = _extract_for_confirmation(message, fields, turn_id)
        if not success:
            retry_count_by_node[current_node_name] = (
                retry_count_by_node.get(current_node_name, 0) + 1
            )
            if retry_count_by_node[current_node_name] >= MAX_RETRIES_PER_NODE:
                tracker.stop("run_turn")
                return _apply_guardrails(_route_to_handoff(result_fields, retry_count_by_node))
            return _apply_guardrails(
                RunResult(
                    next_node=IntakeState.CONFIRMATION.value,
                    assistant_message="I'm sorry, I didn't understand. "
                    + _build_confirmation_text(result_fields),
                    fields=result_fields,
                    call_complete=False,
                    retry_count_by_node=retry_count_by_node,
                )
            )
        retry_count_by_node[current_node_name] = 0
        if action == "summary":
            return _apply_guardrails(_route_to_summary(result_fields, retry_count_by_node))
        return _apply_guardrails(
            RunResult(
                next_node=IntakeState.CONFIRMATION.value,
                assistant_message="Thank you, I've updated that. "
                + _build_confirmation_text(result_fields),
                fields=result_fields,
                call_complete=False,
                retry_count_by_node=retry_count_by_node,
            )
        )

    if current_node_name == IntakeState.SUMMARY.value:
        fhir = _build_fhir_json(fields)
        tracker.stop("run_turn")
        return _apply_guardrails(
            RunResult(
                next_node=IntakeState.COMPLETE.value,
                assistant_message=(
                    "Thank you. Your intake is complete. "
                    "A clinician will review your information shortly.\n\n"
                    f"FHIR-lite Summary:\n{fhir}"
                ),
                fields=fields,
                call_complete=True,
                final_summary=_build_summary(fields),
                retry_count_by_node=retry_count_by_node,
            )
        )

    if current_node_name == IntakeState.HANDOFF.value:
        tracker.stop("run_turn")
        return _apply_guardrails(
            RunResult(
                next_node=IntakeState.COMPLETE.value,
                assistant_message=PROMPTS["handoff"],
                fields=fields,
                call_complete=True,
                final_summary=_build_summary(fields),
                retry_count_by_node=retry_count_by_node,
            )
        )

    # Standard extraction nodes — always attempt extraction even on empty
    # messages so that retry logic works correctly.
    extractor = _EXTRACTORS.get(current_node_name)
    if extractor:
        new_fields, success = extractor(message, fields, turn_id)
        if not success:
            retry_count_by_node[current_node_name] = (
                retry_count_by_node.get(current_node_name, 0) + 1
            )
            if retry_count_by_node[current_node_name] >= MAX_RETRIES_PER_NODE:
                tracker.stop("run_turn")
                return _apply_guardrails(_route_to_handoff(new_fields, retry_count_by_node))
            # Check escalation even on retry — a CRITICAL flag overrides retry
            result = RunResult(
                next_node=current_node_name,
                assistant_message=f"I didn't quite get that. {node.prompt_template}",
                fields=new_fields,
                call_complete=False,
                retry_count_by_node=retry_count_by_node,
            )
            result = _check_and_apply_escalation(result, message)
            tracker.stop("run_turn")
            return _apply_guardrails(result)
        retry_count_by_node[current_node_name] = 0
        fields = new_fields

    # Determine next node
    next_node_name = node.transitions[0] if node.transitions else IntakeState.COMPLETE.value

    if next_node_name == IntakeState.CONFIRMATION.value:
        assistant_message = _build_confirmation_text(fields)
    else:
        next_node = NODE_REGISTRY.get(next_node_name)
        assistant_message = next_node.prompt_template if next_node else ""

    tracker.stop("run_turn")
    result = RunResult(
        next_node=next_node_name,
        assistant_message=assistant_message,
        fields=fields,
        call_complete=False,
        retry_count_by_node=retry_count_by_node,
    )
    result = _check_and_apply_escalation(result, message)
    return _apply_guardrails(result)


def _check_and_apply_escalation(result: RunResult, message: str) -> RunResult:
    """Run red-flag escalation on *message* and mutate *result* if triggered.

    - CRITICAL flags immediately route to handoff with a specific message.
    - HIGH flags are recorded on the result but the intake continues.
    """
    escalation = check_escalation(message)
    if escalation is None:
        return result

    result.handoff_triggered = True
    result.red_flag_severity = escalation.severity
    result.red_flag_id = escalation.flag_id
    result.handoff_reason = escalation.description

    if escalation.severity == "CRITICAL":
        result.next_node = IntakeState.HANDOFF.value
        result.assistant_message = _CRITICAL_HANDOFF_MSG
        result.call_complete = False

    return result


def _route_to_handoff(fields: ExtractedFields, retry_count_by_node: dict[str, int]) -> RunResult:
    return _apply_guardrails(
        RunResult(
            next_node=IntakeState.HANDOFF.value,
            assistant_message=PROMPTS["handoff"],
            fields=fields,
            call_complete=False,
            retry_count_by_node=retry_count_by_node,
        )
    )


def _route_to_summary(fields: ExtractedFields, retry_count_by_node: dict[str, int]) -> RunResult:
    return _apply_guardrails(
        RunResult(
            next_node=IntakeState.SUMMARY.value,
            assistant_message="",
            fields=fields,
            call_complete=False,
            retry_count_by_node=retry_count_by_node,
        )
    )
