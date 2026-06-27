import { useEffect, useRef, type FormEvent } from "react";
import type { Message } from "../types";

interface TranscriptPanelProps {
  messages: Message[];
  input: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  disabled: boolean;
}

export default function TranscriptPanel({
  messages,
  input,
  onInputChange,
  onSend,
  disabled,
}: TranscriptPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) onSend();
  };

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

        <div ref={bottomRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit}>
        <input
          className="input-field"
          type="text"
          placeholder={disabled ? "Session complete" : "Type a message..."}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={disabled}
        />
        <button
          className="btn-send"
          type="submit"
          disabled={disabled || !input.trim()}
        >
          Send
        </button>
      </form>
    </div>
  );
}
