import type { TextIntakeResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function sendMessage(
  sessionId: string,
  message: string,
): Promise<TextIntakeResponse> {
  const body = { message };
  const res = await fetch(`${BASE}/text/intake/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<TextIntakeResponse>;
}
