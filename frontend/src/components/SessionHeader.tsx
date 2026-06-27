import type { IntakeState } from "../types";
import { STATE_LABELS } from "../types";

interface SessionHeaderProps {
  sessionId: string;
  currentState: IntakeState;
  callComplete: boolean;
  onNewSession: () => void;
}

const STATE_COLORS: Record<string, string> = {
  greeting: "#6b7280",
  identity: "#6366f1",
  chief_complaint: "#8b5cf6",
  symptoms: "#a855f7",
  history: "#d946ef",
  allergies: "#ec4899",
  medications: "#f43f5e",
  visit_reason: "#f97316",
  confirmation: "#eab308",
  summary: "#22c55e",
  handoff: "#ef4444",
  complete: "#22c55e",
};

export default function SessionHeader({
  sessionId,
  currentState,
  callComplete,
  onNewSession,
}: SessionHeaderProps) {
  return (
    <header className="session-header">
      <div className="session-header-top">
        <h1 className="session-title">VoiceIntake AI</h1>
        <button className="btn-new-session" onClick={onNewSession}>
          + New Session
        </button>
      </div>

      <div className="session-meta">
        <span className="session-id">
          Session: <code>{sessionId}</code>
        </span>

        <span
          className="state-badge"
          style={{
            backgroundColor: STATE_COLORS[currentState] ?? "#6b7280",
          }}
        >
          {STATE_LABELS[currentState] ?? currentState}
        </span>

        {callComplete && <span className="complete-badge">Complete</span>}
      </div>
    </header>
  );
}
