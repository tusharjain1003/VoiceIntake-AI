from typing import Optional

from pydantic import BaseModel

from backend.fsm.prompts import PROMPTS
from backend.session.models import IntakeState


class StateNode(BaseModel):
    name: str
    prompt_template: str
    extract_field: Optional[str] = None
    transitions: list[str] = []


NODE_REGISTRY: dict[str, StateNode] = {
    IntakeState.GREETING.value: StateNode(
        name=IntakeState.GREETING.value,
        prompt_template=PROMPTS["greeting"],
        extract_field="patient_name",
        transitions=[IntakeState.IDENTITY.value],
    ),
    IntakeState.IDENTITY.value: StateNode(
        name=IntakeState.IDENTITY.value,
        prompt_template=PROMPTS["identity"],
        extract_field="date_of_birth",
        transitions=[IntakeState.CHIEF_COMPLAINT.value],
    ),
    IntakeState.CHIEF_COMPLAINT.value: StateNode(
        name=IntakeState.CHIEF_COMPLAINT.value,
        prompt_template=PROMPTS["chief_complaint"],
        extract_field="chief_complaint",
        transitions=[IntakeState.SYMPTOMS.value],
    ),
    IntakeState.SYMPTOMS.value: StateNode(
        name=IntakeState.SYMPTOMS.value,
        prompt_template=PROMPTS["symptoms"],
        extract_field="symptoms",
        transitions=[IntakeState.MEDICAL_HISTORY.value],
    ),
    IntakeState.MEDICAL_HISTORY.value: StateNode(
        name=IntakeState.MEDICAL_HISTORY.value,
        prompt_template=PROMPTS["medical_history"],
        extract_field="medical_history",
        transitions=[IntakeState.ALLERGIES.value],
    ),
    IntakeState.ALLERGIES.value: StateNode(
        name=IntakeState.ALLERGIES.value,
        prompt_template=PROMPTS["allergies"],
        extract_field="allergies",
        transitions=[IntakeState.MEDICATIONS.value],
    ),
    IntakeState.MEDICATIONS.value: StateNode(
        name=IntakeState.MEDICATIONS.value,
        prompt_template=PROMPTS["medications"],
        extract_field="medications",
        transitions=[IntakeState.VISIT_REASON.value],
    ),
    IntakeState.VISIT_REASON.value: StateNode(
        name=IntakeState.VISIT_REASON.value,
        prompt_template=PROMPTS["visit_reason"],
        extract_field="visit_reason",
        transitions=[IntakeState.SUMMARY.value],
    ),
    IntakeState.SUMMARY.value: StateNode(
        name=IntakeState.SUMMARY.value,
        prompt_template=PROMPTS["summary"],
        extract_field=None,
        transitions=[IntakeState.COMPLETE.value],
    ),
}
