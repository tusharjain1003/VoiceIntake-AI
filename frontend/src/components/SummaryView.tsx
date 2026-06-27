import type { PreVisitSummary } from "../types";

interface SummaryViewProps {
  summary: PreVisitSummary;
}

const SUMMARY_LABELS: Record<keyof PreVisitSummary, string> = {
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

export default function SummaryView({ summary }: SummaryViewProps) {
  const entries = Object.entries(SUMMARY_LABELS) as [keyof PreVisitSummary, string][];
  const hasAny = entries.some(([key]) => summary[key] !== null);

  return (
    <div className="summary-view">
      <h2 className="panel-title">Final Summary</h2>

      {!hasAny && <p className="empty-hint">No summary available.</p>}

      <div className="summary-list">
        {entries.map(([key, label]) => {
          const val = summary[key];
          return (
            <div key={key} className="summary-entry">
              <span className="summary-label">{label}</span>
              <span className="summary-value">{val ?? "—"}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
