interface HandoffBannerProps {
  severity: string | null;
  reason: string | null;
}

export default function HandoffBanner({ severity, reason }: HandoffBannerProps) {
  if (!severity) return null;

  const isCritical = severity === "CRITICAL";

  return (
    <div className={`handoff-banner ${isCritical ? "handoff-banner--critical" : "handoff-banner--high"}`}>
      <div className="handoff-banner__header">
        <span className="handoff-banner__badge">
          {isCritical ? "CRITICAL" : "HIGH"}
        </span>
        <span className="handoff-banner__title">
          {isCritical ? "Red Flag — Immediate Attention Required" : "Red Flag Flagged"}
        </span>
      </div>
      {reason && <p className="handoff-banner__reason">{reason}</p>}
    </div>
  );
}
