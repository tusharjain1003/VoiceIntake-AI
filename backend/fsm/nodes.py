from pydantic import BaseModel

from backend.fsm.prompts import PROMPTS
from backend.session.models import IntakeState


class StateNode(BaseModel):
    name: str
    prompt_template: str
    extract_fields: list[str] = []
    transitions: list[str] = []


NODE_REGISTRY: dict[str, StateNode] = {
    IntakeState.GREETING.value: StateNode(
        name=IntakeState.GREETING.value,
        prompt_template=PROMPTS["greeting"],
        extract_fields=["patient_name"],
        transitions=[IntakeState.IDENTITY.value],
    ),
    IntakeState.IDENTITY.value: StateNode(
        name=IntakeState.IDENTITY.value,
        prompt_template=PROMPTS["identity"],
        extract_fields=["date_of_birth"],
        transitions=[IntakeState.CHIEF_COMPLAINT.value],
    ),
    IntakeState.CHIEF_COMPLAINT.value: StateNode(
        name=IntakeState.CHIEF_COMPLAINT.value,
        prompt_template=PROMPTS["chief_complaint"],
        extract_fields=["chief_complaint"],
        transitions=[IntakeState.SYMPTOMS.value],
    ),
    IntakeState.SYMPTOMS.value: StateNode(
        name=IntakeState.SYMPTOMS.value,
        prompt_template=PROMPTS["symptoms"],
        extract_fields=["symptoms", "symptom_duration"],
        transitions=[IntakeState.HISTORY.value],
    ),
    IntakeState.HISTORY.value: StateNode(
        name=IntakeState.HISTORY.value,
        prompt_template=PROMPTS["history"],
        extract_fields=["medical_history"],
        transitions=[IntakeState.ALLERGIES.value],
    ),
    IntakeState.ALLERGIES.value: StateNode(
        name=IntakeState.ALLERGIES.value,
        prompt_template=PROMPTS["allergies"],
        extract_fields=["allergies"],
        transitions=[IntakeState.MEDICATIONS.value],
    ),
    IntakeState.MEDICATIONS.value: StateNode(
        name=IntakeState.MEDICATIONS.value,
        prompt_template=PROMPTS["medications"],
        extract_fields=["medications"],
        transitions=[IntakeState.VISIT_REASON.value],
    ),
    IntakeState.VISIT_REASON.value: StateNode(
        name=IntakeState.VISIT_REASON.value,
        prompt_template=PROMPTS["visit_reason"],
        extract_fields=["visit_reason"],
        transitions=[IntakeState.CONFIRMATION.value],
    ),
    IntakeState.CONFIRMATION.value: StateNode(
        name=IntakeState.CONFIRMATION.value,
        prompt_template=PROMPTS["confirmation"],
        extract_fields=[],
        transitions=[
            IntakeState.SUMMARY.value,
            IntakeState.CONFIRMATION.value,
            IntakeState.HANDOFF.value,
        ],
    ),
    IntakeState.SUMMARY.value: StateNode(
        name=IntakeState.SUMMARY.value,
        prompt_template="",
        extract_fields=[],
        transitions=[IntakeState.COMPLETE.value],
    ),
    IntakeState.HANDOFF.value: StateNode(
        name=IntakeState.HANDOFF.value,
        prompt_template=PROMPTS["handoff"],
        extract_fields=[],
        transitions=[IntakeState.COMPLETE.value],
    ),
}
