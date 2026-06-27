from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntakeState(str, Enum):
    GREETING = "greeting"
    IDENTITY = "identity"
    CHIEF_COMPLAINT = "chief_complaint"
    SYMPTOMS = "symptoms"
    HISTORY = "history"
    ALLERGIES = "allergies"
    MEDICATIONS = "medications"
    VISIT_REASON = "visit_reason"
    CONFIRMATION = "confirmation"
    SUMMARY = "summary"
    HANDOFF = "handoff"
    COMPLETE = "complete"


class FieldValue(BaseModel):
    value: str
    confidence: float
    source_turn_id: str
    confirmed: bool = False


class ExtractedFields(BaseModel):
    patient_name: Optional[FieldValue] = None
    date_of_birth: Optional[FieldValue] = None
    chief_complaint: Optional[FieldValue] = None
    symptoms: Optional[FieldValue] = None
    symptom_duration: Optional[FieldValue] = None
    medical_history: Optional[FieldValue] = None
    allergies: Optional[FieldValue] = None
    medications: Optional[FieldValue] = None
    visit_reason: Optional[FieldValue] = None


class PreVisitSummary(BaseModel):
    patient_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: Optional[str] = None
    symptom_duration: Optional[str] = None
    medical_history: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    visit_reason: Optional[str] = None


class TextIntakeRequest(BaseModel):
    message: str = ""


class TextIntakeResponse(BaseModel):
    session_id: str
    assistant_message: str
    current_node: IntakeState
    extracted_fields: ExtractedFields
    call_complete: bool = False
    final_summary: Optional[PreVisitSummary] = None
    handoff_triggered: bool = False
    red_flag_severity: Optional[str] = None
    red_flag_id: Optional[str] = None
    handoff_reason: Optional[str] = None


class SessionData(BaseModel):
    session_id: str
    current_node: IntakeState = IntakeState.GREETING
    extracted_fields: ExtractedFields = Field(default_factory=ExtractedFields)
    call_complete: bool = False
    turn_count: int = 0
    retry_count_by_node: dict[str, int] = Field(default_factory=dict)
    handoff_triggered: bool = False
    red_flag_severity: Optional[str] = None
    red_flag_id: Optional[str] = None
    handoff_reason: Optional[str] = None
    latency_logs: list[dict[str, Any]] = Field(default_factory=list)
