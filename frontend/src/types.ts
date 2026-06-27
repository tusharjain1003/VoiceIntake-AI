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

// ---------------------------------------------------------------------------
// WebSocket protocol types
// ---------------------------------------------------------------------------

export type WSClientMessage =
  | { type: "start" }
  | { type: "stop" }
  | { type: "text"; message: string }
  | { type: "voice_start" }
  | { type: "voice_stop" };

export type WSServerMessage =
  | { type: "session_id"; id: string }
  | { type: "agent_text"; text: string }
  | { type: "fields_update"; fields: ExtractedFields }
  | { type: "state_update"; current_node: IntakeState; call_complete: boolean }
  | { type: "summary"; summary: PreVisitSummary | null }
  | {
      type: "handoff";
      handoff_triggered: boolean;
      severity: string | null;
      reason: string | null;
    }
  | { type: "error"; code?: string; message: string }
  | {
      type: "audio_debug";
      chunks_received: number;
      bytes_received: number;
      chunks_forwarded: number;
      bytes_forwarded: number;
      transcript_events: number;
      final_transcripts: number;
      keepalives_sent: number;
    }
  | { type: "transcript"; text: string; is_final: boolean }
  | { type: "tts_start"; content_type: string }
  | { type: "tts_end" }
  | {
      type: "latency";
      turn_id: string;
      metrics: LatencyMetrics;
    };

export interface LatencyMetrics {
  stt_final_ms: number | null;
  fsm_ms: number | null;
  tts_ms: number | null;
  total_response_ms: number | null;
  timestamp: number;
}

export interface LatencyEntry {
  turn_number: number;
  stt_final_ms: number | null;
  fsm_ms: number | null;
  tts_ms: number | null;
  total_response_ms: number | null;
  timestamp: number;
}

export type OrbState = "idle" | "listening" | "processing" | "speaking" | "handoff";

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
