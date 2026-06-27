import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Browser microphone capture hook.
 *
 * Uses MediaRecorder with `audio/webm;codecs=opus` when supported.
 * Sends ~250ms chunks as binary Blob over the provided WebSocket.
 *
 * Does NOT use AudioWorklet or PCM. The browser sends WebM/Opus chunks
 * which a downstream server-side STT pipeline (Deepgram etc.) can consume.
 */

interface UseMicrophoneOptions {
  ws: WebSocket | null;
}

export type MicStatus = "idle" | "requesting" | "active" | "error" | "unsupported";
export type MicError = { message: string } | null;

const CHUNK_MS = 250;
const PREFERRED_MIME = "audio/webm;codecs=opus";

export default function useMicrophone({ ws }: UseMicrophoneOptions) {
  const [status, setStatus] = useState<MicStatus>("idle");
  const [error, setError] = useState<MicError>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const bytesSentRef = useRef(0);
  const chunkCountRef = useRef(0);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
    setStatus("idle");
    setError(null);
    bytesSentRef.current = 0;
    chunkCountRef.current = 0;
  }, []);

  const start = useCallback(async () => {
    setStatus("requesting");
    setError(null);

    // Check MediaRecorder support
    if (
      typeof MediaRecorder === "undefined" ||
      (MediaRecorder.isTypeSupported &&
        !MediaRecorder.isTypeSupported(PREFERRED_MIME))
    ) {
      setStatus("unsupported");
      setError({ message: "MediaRecorder with WebM/Opus not supported in this browser." });
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setStatus("active");

      const recorder = new MediaRecorder(stream, {
        mimeType: PREFERRED_MIME,
      });
      recorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size === 0) return;

        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(event.data);
          bytesSentRef.current += event.data.size;
          chunkCountRef.current += 1;
        }
      };

      recorder.start(CHUNK_MS);
    } catch (err) {
      setStatus("error");
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setError({ message: "Microphone permission denied. Allow mic access or use text input." });
      } else if (err instanceof DOMException && err.name === "NotFoundError") {
        setError({ message: "No microphone found. Connect a mic or use text input." });
      } else {
        setError({ message: err instanceof Error ? err.message : "Failed to start microphone." });
      }
    }
  }, []);

  // Keep a ref to the latest ws so the recorder closure sees the current value
  const wsRef = useRef(ws);
  wsRef.current = ws;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  // Auto-stop when ws disconnects
  useEffect(() => {
    if (!ws && status === "active") {
      stop();
    }
  }, [ws, status, stop]);

  return { status, start, stop, error, bytesSent: bytesSentRef.current, chunkCount: chunkCountRef.current };
}
