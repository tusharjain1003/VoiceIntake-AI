import { useCallback, useEffect, useRef, useState } from "react";
import type { WSServerMessage } from "./types";

type ConnectionStatus = "idle" | "connecting" | "connected" | "closed" | "error";

interface UseIntakeSocketOptions {
  onMessage: (msg: WSServerMessage) => void;
  onStatusChange?: (status: ConnectionStatus) => void;
}

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "";

export default function useIntakeSocket({
  onMessage,
  onStatusChange,
}: UseIntakeSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  const setStatusSafe = useCallback((s: ConnectionStatus) => {
    setStatus(s);
    onStatusChangeRef.current?.(s);
  }, []);

  const connect = useCallback(
    (sessionId: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = WS_BASE
        ? WS_BASE.replace(/^http/, "ws")
        : `${protocol}//${window.location.host}`;
      const url = `${host}/ws/intake/${sessionId}`;

      setStatusSafe("connecting");

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatusSafe("connected");
        ws.send(JSON.stringify({ type: "start" }));
      };

      ws.onmessage = (event) => {
        try {
          const msg: WSServerMessage = JSON.parse(event.data);
          onMessageRef.current(msg);
        } catch {
          // skip unparseable messages
        }
      };

      ws.onclose = () => {
        setStatusSafe("closed");
        wsRef.current = null;
      };

      ws.onerror = () => {
        setStatusSafe("error");
      };
    },
    [setStatusSafe],
  );

  const sendText = useCallback((text: string) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "text", message: text }));
    }
  }, []);

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    if (ws) {
      ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
      wsRef.current = null;
    }
    setStatusSafe("idle");
  }, [setStatusSafe]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { status, connect, sendText, disconnect, wsRef };
}
