export type IntakeState =
  | "greeting"
  | "identity"
  | "chief_complaint"
  | "symptoms"
  | "history"
  | "allergies"
  | "medications"
  | "visit_reason"
  | "confirmation"
  | "summary"
  | "handoff"
  | "complete";

export interface FieldValue {
  value: string;
  confidence: number;
  source_turn_id: string;
  confirmed: boolean;
}

export interface ExtractedFields {
  patient_name: FieldValue | null;
  date_of_birth: FieldValue | null;
  chief_complaint: FieldValue | null;
  symptoms: FieldValue | null;
  symptom_duration: FieldValue | null;
  medical_history: FieldValue | null;
  allergies: FieldValue | null;
  medications: FieldValue | null;
  visit_reason: FieldValue | null;
}

export interface PreVisitSummary {
  patient_name: string | null;
  date_of_birth: string | null;
  chief_complaint: string | null;
  symptoms: string | null;
  symptom_duration: string | null;
  medical_history: string | null;
  allergies: string | null;
  medications: string | null;
  visit_reason: string | null;
}

export interface TextIntakeResponse {
  session_id: string;
  assistant_message: string;
  current_node: IntakeState;
  extracted_fields: ExtractedFields;
  call_complete: boolean;
  final_summary: PreVisitSummary | null;
  handoff_triggered: boolean;
  red_flag_severity: string | null;
  red_flag_id: string | null;
  handoff_reason: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export const STATE_LABELS: Record<IntakeState, string> = {
  greeting: "Greeting",
  identity: "Identity",
  chief_complaint: "Chief Complaint",
  symptoms: "Symptoms",
  history: "History",
  allergies: "Allergies",
  medications: "Medications",
  visit_reason: "Visit Reason",
  confirmation: "Confirmation",
  summary: "Summary",
  handoff: "Handoff",
  complete: "Complete",
};
