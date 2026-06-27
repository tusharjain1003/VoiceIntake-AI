import type { OrbState } from "../types";

interface VoiceOrbProps {
  state: OrbState;
  onStart: () => void;
  onStop: () => void;
  disabled: boolean;
}

const STATE_LABELS: Record<OrbState, string> = {
  idle: "Start Voice Intake",
  listening: "Listening…",
  processing: "Processing…",
  speaking: "Speaking…",
  handoff: "Handoff",
};

export default function VoiceOrb({ state, onStart, onStop, disabled }: VoiceOrbProps) {
  if (state === "idle") {
    return (
      <div className="voice-orb-container">
        <button
          className="voice-orb-button voice-orb-button--idle"
          onClick={onStart}
          disabled={disabled}
          title="Start voice intake"
        >
          <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
            <path
              d="M24 6a6 6 0 0 0-6 6v12a6 6 0 0 0 12 0V12a6 6 0 0 0-6-6z"
              fill="currentColor"
            />
            <path
              d="M14 22v2a10 10 0 0 0 20 0v-2"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
            />
            <rect x="22" y="34" width="4" height="8" rx="2" fill="currentColor" />
          </svg>
        </button>
        <span className="voice-orb-label">{STATE_LABELS[state]}</span>
      </div>
    );
  }

  return (
    <div className="voice-orb-container">
      <button
        className={`voice-orb-button voice-orb-button--${state}`}
        onClick={onStop}
        title={`Stop voice intake (${state})`}
      >
        <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
          {state === "listening" && (
            <>
              <circle cx="24" cy="24" r="16" stroke="currentColor" strokeWidth="3" fill="none" />
              <circle cx="24" cy="24" r="6" fill="currentColor" />
              <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="1" fill="none" opacity="0.3" />
            </>
          )}
          {state === "processing" && (
            <circle cx="24" cy="24" r="16" stroke="currentColor" strokeWidth="3" fill="none" />
          )}
          {state === "speaking" && (
            <>
              <path d="M16 20v8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              <path d="M22 16v16" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              <path d="M28 18v12" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              <path d="M34 21v6" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </>
          )}
          {state === "handoff" && (
            <text
              x="24"
              y="28"
              textAnchor="middle"
              fontSize="14"
              fontWeight="700"
              fill="currentColor"
            >
              !
            </text>
          )}
        </svg>
      </button>
      <span className="voice-orb-label">{STATE_LABELS[state]}</span>
    </div>
  );
}
