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
- Day 3 milestone: a working text loop that can collect a full intake and produce a summary. De-risks the project.

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

**Decision:** Redis for hot session state (fast reads/writes per turn); Postgres for durable storage (completed sessions, transcripts, summaries).

**Rationale:**
- Redis TTL auto-cleans abandoned sessions.
- Postgres is the source of truth for audit and later RAG ingestion.
- Separation avoids schema migration churn on Redis.

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
