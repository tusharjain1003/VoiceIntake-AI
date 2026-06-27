import { useCallback, useRef, useState } from "react";
import { sendMessage } from "./api";
import FieldsPanel from "./components/FieldsPanel";
import SessionHeader from "./components/SessionHeader";
import SummaryView from "./components/SummaryView";
import TranscriptPanel from "./components/TranscriptPanel";
import type {
  ExtractedFields,
  IntakeState,
  Message,
  PreVisitSummary,
} from "./types";
import "./App.css";

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
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const handleNewSession = useCallback(() => {
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
  }, []);

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

    try {
      const sid =
        sessionIdRef.current === "new" ? "new" : sessionIdRef.current;
      const res = await sendMessage(sid, msg);

      if (sessionIdRef.current === "new") {
        setSessionId(res.session_id);
        sessionIdRef.current = res.session_id;
      }

      setCurrentState(res.current_node);
      setFields(res.extracted_fields);
      setCallComplete(res.call_complete);
      if (res.final_summary) setSummary(res.final_summary);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: res.assistant_message,
      };
      setMessages((prev) => [...prev, assistantMsg]);
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
    } finally {
      setLoading(false);
    }
  }, [input, loading]);

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
          <TranscriptPanel
            messages={messages}
            input={input}
            onInputChange={setInput}
            onSend={handleSend}
            disabled={callComplete || loading}
          />
        </section>

        <aside className="panel panel--right">
          <div className="status-panel">
            <h2 className="panel-title">Status</h2>
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
          </div>
        </aside>
      </main>
    </div>
  );
}
