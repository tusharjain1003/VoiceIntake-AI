import { useMemo } from "react";
import type { LatencyEntry } from "../types";

interface Props {
  logs: LatencyEntry[];
}

const BAR_MAX = 5000; // scale 0..5000ms to bar width
const COLORS: { stt: string; fsm: string; tts: string; total: string } = {
  stt: "#3b82f6",
  fsm: "#22c55e",
  tts: "#f97316",
  total: "#a855f7",
};

function p95(values: (number | null)[]): number | null {
  const nums = values.filter((v): v is number => v !== null);
  if (nums.length === 0) return null;
  nums.sort((a, b) => a - b);
  const idx = Math.max(0, Math.ceil(nums.length * 0.95) - 1);
  const val = nums[idx];
  return val ?? null;
}

function Bar({ label, ms, color }: { label: string; ms: number | null; color: string }) {
  if (ms === null) {
    return (
      <div className="latency-bar-row">
        <span className="latency-bar-label">{label}</span>
        <span className="latency-bar-track">
          <span className="latency-bar-fill" style={{ width: 0, background: color }} />
        </span>
        <span className="latency-bar-ms">—</span>
      </div>
    );
  }
  const pct = Math.min((ms / BAR_MAX) * 100, 100);
  return (
    <div className="latency-bar-row">
      <span className="latency-bar-label">{label}</span>
      <span className="latency-bar-track">
        <span
          className="latency-bar-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <span className="latency-bar-ms">{ms.toFixed(0)}ms</span>
    </div>
  );
}

export default function LatencyBar({ logs }: Props) {
  const last5 = useMemo(() => logs.slice(-5).reverse(), [logs]);

  const p95Stt = useMemo(() => p95(logs.map((l) => l.stt_final_ms)), [logs]);
  const p95Fsm = useMemo(() => p95(logs.map((l) => l.fsm_ms)), [logs]);
  const p95Tts = useMemo(() => p95(logs.map((l) => l.tts_ms)), [logs]);
  const p95Total = useMemo(() => p95(logs.map((l) => l.total_response_ms)), [logs]);

  const showP95 = logs.length >= 5;

  if (logs.length === 0) return null;

  return (
    <div className="latency-panel">
      <h2 className="panel-title">Latency (last 5 turns)</h2>

      {last5.map((turn) => (
        <div key={turn.turn_number} className="latency-turn">
          <div className="latency-turn-header">Turn {turn.turn_number}</div>
          <Bar label="STT" ms={turn.stt_final_ms} color={COLORS.stt} />
          <Bar label="FSM" ms={turn.fsm_ms} color={COLORS.fsm} />
          <Bar label="TTS" ms={turn.tts_ms} color={COLORS.tts} />
          <Bar label="Total" ms={turn.total_response_ms} color={COLORS.total} />
        </div>
      ))}

      {showP95 && (
        <div className="latency-p95">
          <div className="latency-p95-header">P95 ({logs.length} turns)</div>
          <Bar label="STT" ms={p95Stt} color={COLORS.stt} />
          <Bar label="FSM" ms={p95Fsm} color={COLORS.fsm} />
          <Bar label="TTS" ms={p95Tts} color={COLORS.tts} />
          <Bar label="Total" ms={p95Total} color={COLORS.total} />
        </div>
      )}
    </div>
  );
}
