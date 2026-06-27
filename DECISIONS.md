# Design Decisions

## 1. FSM over Conversational Graph

**Decision:** Use an explicit finite state machine (`NODE_REGISTRY`) instead of an LLM-driven graph that re-enters from the greeting every turn.

**Rationale:**
- Deterministic flow ensures every patient is asked the same required fields.
- No risk of the LLM skipping a section or looping back to "Hi, what's your name?" mid-conversation.
- Transitions are explicit and auditable — a supervisor can inspect which state the session is in.
- Easier to test: every state + input → next state is a unit test.

## 2. Text FSM First, Voice Later

**Decision:** Build and validate the entire FSM with a text-only interface before adding voice.

**Rationale:**
- Core logic (state transitions, guardrails, field extraction, summary generation) is independent of modality.
- Voice adds latency, error modes (transcription noise), and browser API complexity.
- De-risks the project by proving correctness of the intake flow before adding audio.

## 3. FieldValue Metadata

**Decision:** Every collected field stores `value`, `confidence`, `source_turn_id`, `confirmed`.

**Rationale:**
- Enables confidence-based re-asking ("I didn't quite catch that…")
- Full audit trail from raw transcript → extracted field.
- `confirmed` flag allows double-checking before finalizing.

## 4. Guardrail Categories

**Decision:** Structured guardrail categories, not free-text refusal.

**Categories:**
| Category | Trigger |
|----------|---------|
| `DIAGNOSIS` | Patient asks "what do I have?" |
| `TREATMENT_RECOMMENDATION` | Patient asks "what should I take?" |
| `MEDICATION_CHANGE` | Patient asks "should I stop my meds?" |
| `TEST_RESULT_INTERPRETATION` | Patient asks "what does this lab mean?" |
| `URGENCY_CLAIM_TO_PATIENT` | Operator tells patient "you're fine" or "this is serious" |
| `REASSURANCE_OR_DISMISSAL` | Operator dismisses a symptom without clinician review |

**Rationale:** Categorical routing makes guardrails testable and auditable. Each category maps to a specific scripted response + optional human handoff.

## 5. Postgres + Redis

**Decision:** Redis for hot session state (fast reads/writes per turn); Postgres for durable audit (session snapshots, transcripts, safety/escalation events, latency metrics, and summaries written on **every turn**).

**Rationale:**
- Redis TTL auto-cleans abandoned sessions.
- Postgres is the source of truth for audit and later RAG ingestion.
- Separation avoids schema migration churn on Redis.
- The `backend/db/repository.py` module encapsulates all Postgres writes. Each method is best-effort — failures log a warning but never block the user flow. Summary writes log errors at `ERROR` level to make data-loss events visible.

**Status:** Implemented. Both REST (`/text/intake/{session_id}`) and WebSocket (`/ws/intake/{session_id}`) paths persist on every `run_turn`. The `/health` endpoint reports `db_available` and `redis_available` flags.

## 6. Full-Audio TTS First, Streaming Later

**Decision:** Send complete audio blobs from ElevenLabs before implementing streaming.

**Rationale:**
- Simpler error handling (no chunk ordering, no partial playback).
- Streaming can be swapped in without changing the FSM or message protocol.

## 7. No ICD-10, No EHR Integration

**Decision:** Explicitly out of scope.

**Rationale:**
- ICD-10 coding requires medical coding expertise to validate.
- EHR integration is highly vendor-specific and would dominate scope.
- The output is a structured summary for manual clinician review — not an automated EHR submission.

## 8. WebM/Opus over Raw PCM

**Decision:** Use the browser's native `MediaRecorder` with `audio/webm;codecs=opus` instead of capturing raw PCM via `AudioWorklet`.

**Rationale:**
- Zero client-side audio processing code — the browser handles encoding.
- Deepgram accepts WebM/Opus directly via its streaming API.
- 250ms chunks provide low enough latency without complex buffering.
- PCM capture would require custom WebAudio wiring and adds deployment risk.

## 9. Deepgram over Whisper

**Decision:** Use Deepgram for streaming STT instead of self-hosting Whisper.

**Rationale:**
- Deepgram handles the streaming endpoint, WebSocket framing, and diarization natively.
- Self-hosted Whisper would require GPU infrastructure and significant ops overhead.
- Deepgram's Nova-2 model provides accuracy competitive with Whisper Large-v3.
- The project has no requirements for on-premise or air-gapped deployment.

## 10. Medication RAG Deferred

**Decision:** Medication lookup (RAG over drug database) is deferred to a future milestone.

**Rationale:**
- Core FSM logic, field extraction, and summary generation work without it.
- Medication data would add schema and ingestion complexity without blocking the demo.
- A simple free-text capture of "medications" suffices for the initial clinical intake loop.

## 11. Text-Only Evals for Scale

**Decision:** Run offline evaluations using a deterministic patient simulator over the text-only REST endpoint, without TTS/STT.

**Rationale:**
- Eliminates API costs for STT/TTS during eval runs — enables running 500+ conversations cheaply.
- Core FSM correctness is independent of speech modality.
- Deterministic patient responses (templates per node) make results reproducible.
- Per-turn timing metrics capture the LLM + FSM portion of latency, which is the dominant variable.

## 12. Fail Visible on Session Store Outage

**Decision:** When Redis is unavailable, the session manager raises `SessionStoreUnavailableError` rather than silently creating blank sessions.

**Rationale:**
- Previously, `_save()` silently skipped writes and `_load()` returned `None` when Redis was down. A follow-up request would create a fresh blank session, silently corrupting the intake flow.
- The REST endpoint returns HTTP 503 with a descriptive message.
- The WebSocket handler sends a JSON error event and closes with code 1011.
- For local development without Docker, `DEV_MODE=true` switches to an in-memory store (`MemorySessionManager`) that does not persist across restarts but allows the app to start without Redis.
- In production (`dev_mode=false`), the app will not start at all if Redis is unavailable, preventing silent data loss.
