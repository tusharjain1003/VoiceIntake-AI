import { useEffect, useRef } from "react";
import type { Message } from "../types";

interface TranscriptPanelProps {
  messages: Message[];
  interimTranscript?: string;
}

export default function TranscriptPanel({ messages, interimTranscript = "" }: TranscriptPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="transcript-panel">
      <h2 className="panel-title">Transcript</h2>

      <div className="message-list">
        {messages.length === 0 && (
          <p className="empty-hint">Start a session to begin the intake.</p>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`message message--${msg.role}`}>
            <span className="message-role">
              {msg.role === "assistant" ? "Assistant" : "You"}
            </span>
            <p className="message-text">{msg.text}</p>
          </div>
        ))}

        {interimTranscript && (
          <div className="message message--user message--interim">
            <span className="message-role">You</span>
            <p className="message-text">{interimTranscript}</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
