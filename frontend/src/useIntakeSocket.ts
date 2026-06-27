import { useCallback, useEffect, useRef, useState } from "react";
import type { WSServerMessage } from "./types";

type ConnectionStatus = "idle" | "connecting" | "connected" | "closed" | "error";

interface UseIntakeSocketOptions {
  onMessage: (msg: WSServerMessage) => void;
  onStatusChange?: (status: ConnectionStatus) => void;
  onTtsPlaying?: (playing: boolean) => void;
}

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "";

export default function useIntakeSocket({
  onMessage,
  onStatusChange,
  onTtsPlaying,
}: UseIntakeSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;
  const onTtsPlayingRef = useRef(onTtsPlaying);
  onTtsPlayingRef.current = onTtsPlaying;

  // TTS internal state
  const ttsChunksRef = useRef<ArrayBuffer[]>([]);
  const ttsContentTypeRef = useRef("audio/mpeg");
  const expectingBinaryRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stopCurrentPlayback = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    onTtsPlayingRef.current?.(false);
  }, []);

  const playTtsAudio = useCallback(
    (chunks: ArrayBuffer[], contentType: string) => {
      if (chunks.length === 0) return;

      const blob = new Blob(chunks, { type: contentType });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      onTtsPlayingRef.current?.(true);

      audio.addEventListener("ended", () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        onTtsPlayingRef.current?.(false);
      });

      audio.addEventListener("error", () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        onTtsPlayingRef.current?.(false);
      });

      audio.play().catch(() => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        onTtsPlayingRef.current?.(false);
      });
    },
    [],
  );

  const setStatusSafe = useCallback((s: ConnectionStatus) => {
    setStatus(s);
    onStatusChangeRef.current?.(s);
  }, []);

  const connect = useCallback(
    (sessionId: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      stopCurrentPlayback();

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = WS_BASE
        ? WS_BASE.replace(/^http/, "ws")
        : `${protocol}//${window.location.host}`;
      const url = `${host}/ws/intake/${sessionId}`;

      setStatusSafe("connecting");

      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setStatusSafe("connected");
        ws.send(JSON.stringify({ type: "start" }));
      };

      ws.onmessage = (event) => {
        // Binary data — TTS audio chunk (binaryType = "arraybuffer")
        if (event.data instanceof ArrayBuffer) {
          if (expectingBinaryRef.current) {
            ttsChunksRef.current.push(event.data);
          }
          return;
        }

        // Text data — JSON
        try {
          const msg: WSServerMessage = JSON.parse(event.data);

          if (msg.type === "tts_start") {
            expectingBinaryRef.current = true;
            ttsChunksRef.current = [];
            ttsContentTypeRef.current = msg.content_type;
            stopCurrentPlayback();
            onMessageRef.current(msg);
            return;
          }

          if (msg.type === "tts_end") {
            expectingBinaryRef.current = false;
            const chunks = ttsChunksRef.current;
            const contentType = ttsContentTypeRef.current;
            ttsChunksRef.current = [];
            playTtsAudio(chunks, contentType);
            onMessageRef.current(msg);
            return;
          }

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
    [setStatusSafe, stopCurrentPlayback, playTtsAudio],
  );

  const sendText = useCallback((text: string) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "text", message: text }));
    }
  }, []);

  const disconnect = useCallback(() => {
    stopCurrentPlayback();
    const ws = wsRef.current;
    if (ws) {
      ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
      wsRef.current = null;
    }
    setStatusSafe("idle");
  }, [setStatusSafe, stopCurrentPlayback]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { status, connect, sendText, disconnect, wsRef };
}
