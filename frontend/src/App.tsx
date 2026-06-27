import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { sendMessage } from "./api";
import FieldsPanel from "./components/FieldsPanel";
import HandoffBanner from "./components/HandoffBanner";
import LatencyBar from "./components/LatencyBar";
import SessionHeader from "./components/SessionHeader";
import SummaryView from "./components/SummaryView";
import TranscriptPanel from "./components/TranscriptPanel";
import VoiceOrb from "./components/VoiceOrb";
import useIntakeSocket from "./useIntakeSocket";
import useMicrophone from "./useMicrophone";
import type {
  ExtractedFields,
  IntakeState,
  LatencyEntry,
  Message,
  OrbState,
  PreVisitSummary,
  WSServerMessage,
} from "./types";
import "./App.css";

type Mode = "rest" | "ws";

export default function App() {
  const [sessionId, setSessionId] = useState("new");
  const [currentState, setCurrentState] = useState<IntakeState>("greeting");
  const [messages, setMessages] = useState<Message[]>([]);
  const [fields, setFields] = useState<ExtractedFields>({
    patient_name: null,
    date_of_birth: null,
    chief_complaint: null,
    symptoms: null,
    symptom_duration: null,
    medical_history: null,
    allergies: null,
    medications: null,
    visit_reason: null,
  });
  const [summary, setSummary] = useState<PreVisitSummary | null>(null);
  const [callComplete, setCallComplete] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [handoffTriggered, setHandoffTriggered] = useState(false);
  const [redFlagSeverity, setRedFlagSeverity] = useState<string | null>(null);
  const [handoffReason, setHandoffReason] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("ws");
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [latencyLogs, setLatencyLogs] = useState<LatencyEntry[]>([]);
  const [interimTranscript, setInterimTranscript] = useState("");
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const applyResponse = useCallback(
    (res: {
      current_node: IntakeState;
      extracted_fields: ExtractedFields;
      call_complete: boolean;
      final_summary: PreVisitSummary | null;
      handoff_triggered: boolean;
      red_flag_severity: string | null;
      handoff_reason: string | null;
      assistant_message: string;
    }) => {
      setCurrentState(res.current_node);
      setFields(res.extracted_fields);
      setCallComplete(res.call_complete);
      if (res.final_summary) setSummary(res.final_summary);
      setHandoffTriggered(res.handoff_triggered);
      setRedFlagSeverity(res.red_flag_severity);
      setHandoffReason(res.handoff_reason);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: res.assistant_message,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    },
    [],
  );

  const ttsActiveRef = useRef(false);

  const handleTtsPlaying = useCallback((playing: boolean) => {
    ttsActiveRef.current = playing;
    if (!playing) {
      setOrbState("listening");
    }
  }, []);

  const handleWsMessage = useCallback(
    (msg: WSServerMessage) => {
      if (msg.type === "session_id") {
        setSessionId(msg.id);
        sessionIdRef.current = msg.id;
        return;
      }

      if (msg.type === "agent_text") {
        const aiMsg: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          text: msg.text,
        };
        setMessages((prev) => [...prev, aiMsg]);
        return;
      }

      if (msg.type === "fields_update") {
        setFields(msg.fields);
        return;
      }

      if (msg.type === "state_update") {
        setCurrentState(msg.current_node);
        setCallComplete(msg.call_complete);
        return;
      }

      if (msg.type === "summary") {
        if (msg.summary) setSummary(msg.summary);
        return;
      }

      if (msg.type === "handoff") {
        setHandoffTriggered(msg.handoff_triggered);
        setRedFlagSeverity(msg.severity);
        setHandoffReason(msg.reason);
        setOrbState("handoff");
        return;
      }

      if (msg.type === "tts_start") {
        setOrbState("speaking");
        return;
      }

      if (msg.type === "tts_end") {
        return;
      }

      if (msg.type === "audio_debug") {
        if (import.meta.env.DEV) {
          console.log("[AudioDebug]", msg);
        }
        return;
      }

      if (msg.type === "latency") {
        setLatencyLogs((prev) => [
          ...prev,
          { turn_number: prev.length + 1, ...msg.metrics },
        ]);
        return;
      }

      if (msg.type === "transcript") {
        if (msg.is_final) {
          const userMsg: Message = {
            id: crypto.randomUUID(),
            role: "user",
            text: msg.text,
          };
          setMessages((prev) => [...prev, userMsg]);
          setInterimTranscript("");
        } else {
          setInterimTranscript(msg.text);
        }
        return;
      }

      if (msg.type === "error") {
        const label = msg.code ? `[${msg.code}] ` : "";
        const errMsg: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          text: `Error: ${label}${msg.message}`,
        };
        setMessages((prev) => [...prev, errMsg]);
        return;
      }
    },
    [],
  );

  const { status: wsStatus, connect, sendText, disconnect, wsRef } =
    useIntakeSocket({
      onMessage: handleWsMessage,
      onTtsPlaying: handleTtsPlaying,
    });

  const sendJson = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, [wsRef]);

  const mic = useMicrophone({ ws: wsRef.current });

  const waitForWsOpen = useCallback(async (timeoutMs = 3000): Promise<boolean> => {
    const started = performance.now();
    while (performance.now() - started < timeoutMs) {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    return false;
  }, [wsRef]);

  // Reset orb state when mic fails (permission denied, no device, etc.)
  useEffect(() => {
    if (mic.status === "error" || mic.status === "unsupported") {
      setOrbState("idle");
    }
  }, [mic.status]);

  const resetState = useCallback(() => {
    setSessionId("new");
    setCurrentState("greeting");
    setMessages([]);
    setFields({
      patient_name: null,
      date_of_birth: null,
      chief_complaint: null,
      symptoms: null,
      symptom_duration: null,
      medical_history: null,
      allergies: null,
      medications: null,
      visit_reason: null,
    });
    setSummary(null);
    setCallComplete(false);
    setInput("");
    setLoading(false);
    setHandoffTriggered(false);
    setRedFlagSeverity(null);
    setHandoffReason(null);
    setOrbState("idle");
    setLatencyLogs([]);
    setInterimTranscript("");
  }, []);

  const handleNewSession = useCallback(() => {
    mic.stop();
    disconnect();
    resetState();
  }, [disconnect, resetState, mic]);

  const handleSend = useCallback(async () => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput("");

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text: msg,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setOrbState("processing");

    try {
      if (mode === "ws") {
        if (wsStatus === "connected") {
          sendText(msg);
          setLoading(false);
          return;
        }
        const sid =
          sessionIdRef.current === "new" ? "new" : sessionIdRef.current;
        connect(sid);
      }

      const sid =
        sessionIdRef.current === "new" ? "new" : sessionIdRef.current;
      const res = await sendMessage(sid, msg);

      if (sessionIdRef.current === "new") {
        setSessionId(res.session_id);
        sessionIdRef.current = res.session_id;
      }

      if (mode === "ws" && wsStatus !== "connected") {
        connect(res.session_id);
      }

      applyResponse(res);
      setOrbState("speaking");
      setTimeout(() => setOrbState((prev) => (prev === "speaking" ? "idle" : prev)), 800);
    } catch (err) {
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text:
          err instanceof Error
            ? `Error: ${err.message}`
            : "An unexpected error occurred.",
      };
      setMessages((prev) => [...prev, errorMsg]);
      setOrbState("idle");
    } finally {
      setLoading(false);
    }
  }, [input, loading, mode, wsStatus, sendText, connect, applyResponse]);

  const handleStartVoice = useCallback(async () => {
    if (orbState !== "idle") return;

    if (mode !== "ws") {
      setMode("ws");
    }

    if (wsStatus !== "connected") {
      const sid =
        sessionIdRef.current === "new" ? "new" : sessionIdRef.current;
      connect(sid);
      const connected = await waitForWsOpen();
      if (!connected) {
        const errorMsg: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "Error: WebSocket did not connect. Please try again or use text input.",
        };
        setMessages((prev) => [...prev, errorMsg]);
        setOrbState("idle");
        return;
      }
    }

    sendJson({ type: "voice_start" });
    setOrbState("listening");
    mic.start();
  }, [orbState, mode, wsStatus, connect, waitForWsOpen, mic, sendJson]);

  const handleStopVoice = useCallback(() => {
    sendJson({ type: "voice_stop" });
    mic.stop();
    setOrbState("idle");
  }, [mic, sendJson]);

  const toggleMode = useCallback(() => {
    setMode((prev) => (prev === "ws" ? "rest" : "ws"));
  }, []);

  const handleTextSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  return (
    <div className="app">
      <SessionHeader
        sessionId={sessionId}
        currentState={currentState}
        callComplete={callComplete}
        onNewSession={handleNewSession}
      />

      <main className="main-layout">
        <aside className="panel panel--left">
          <FieldsPanel fields={fields} />
          {summary && <SummaryView summary={summary} />}
        </aside>

        <section className="panel panel--center">
          <TranscriptPanel messages={messages} interimTranscript={interimTranscript} />
        </section>

        <aside className="panel panel--right">
          {handoffTriggered && (
            <HandoffBanner severity={redFlagSeverity} reason={handoffReason} />
          )}

          <div className="status-panel">
            <h2 className="panel-title">Session</h2>
            <div className="status-item">
              <span className="status-label">Current Node</span>
              <span className="status-value">{currentState}</span>
            </div>
            <div className="status-item">
              <span className="status-label">Complete</span>
              <span className="status-value">
                {callComplete ? "Yes" : "No"}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Messages</span>
              <span className="status-value">{messages.length}</span>
            </div>
            <div className="status-item">
              <span className="status-label">Mode</span>
              <span className="status-value">{mode.toUpperCase()}</span>
            </div>
            <div className="status-item">
              <span className="status-label">WS Status</span>
              <span className="status-value">{wsStatus}</span>
            </div>
            <div className="status-item">
              <span className="status-label">Mic</span>
              <span className="status-value">{mic.status}</span>
            </div>
          </div>

          {mic.error && (
            <div className="mic-error-banner">
              {mic.error.message}
            </div>
          )}

          <VoiceOrb
            state={handoffTriggered ? "handoff" : orbState}
            onStart={handleStartVoice}
            onStop={handleStopVoice}
            disabled={callComplete}
          />

          <form className="text-fallback-area" onSubmit={handleTextSubmit}>
            <input
              className="input-field"
              type="text"
              placeholder={callComplete ? "Session complete" : "Type as fallback..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={callComplete}
            />
            <button
              className="btn-send"
              type="submit"
              disabled={callComplete || loading || !input.trim()}
            >
              {loading ? "..." : "Send"}
            </button>
          </form>

          <button className="btn-reset-session" onClick={handleNewSession}>
            Reset Session
          </button>

          <button className="btn-mode-toggle" onClick={toggleMode}>
            Switch to {mode === "ws" ? "REST" : "WebSocket"}
          </button>

          <LatencyBar logs={latencyLogs} />
        </aside>
      </main>
    </div>
  );
}
