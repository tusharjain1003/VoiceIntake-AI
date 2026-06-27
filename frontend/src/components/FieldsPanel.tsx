import type { ExtractedFields } from "../types";

interface FieldsPanelProps {
  fields: ExtractedFields;
}

const FIELD_LABELS: Record<keyof ExtractedFields, string> = {
  patient_name: "Patient Name",
  date_of_birth: "Date of Birth",
  chief_complaint: "Chief Complaint",
  symptoms: "Symptoms",
  symptom_duration: "Symptom Duration",
  medical_history: "Medical History",
  allergies: "Allergies",
  medications: "Medications",
  visit_reason: "Visit Reason",
};

export default function FieldsPanel({ fields }: FieldsPanelProps) {
  const entries = Object.entries(FIELD_LABELS) as [keyof ExtractedFields, string][];
  const hasAny = entries.some(([key]) => fields[key] !== null);

  return (
    <div className="fields-panel">
      <h2 className="panel-title">Extracted Fields</h2>

      {!hasAny && <p className="empty-hint">No fields extracted yet.</p>}

      <div className="fields-list">
        {entries.map(([key, label]) => {
          const fv = fields[key];
          return (
            <div
              key={key}
              className={`field-entry ${fv ? "field-entry--filled" : ""}`}
            >
              <span className="field-label">{label}</span>
              <span className="field-value">
                {fv ? fv.value : <em>—</em>}
              </span>
              {fv && (
                <span className="field-meta">
                  {Math.round(fv.confidence * 100)}% &middot;{" "}
                  {fv.confirmed ? "confirmed" : "unconfirmed"}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
