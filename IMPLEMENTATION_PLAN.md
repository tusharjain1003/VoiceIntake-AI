# Implementation Plan

## Phases

### Phase 0 — Foundation (Days 1–3)

- [ ] Project scaffolding (Python project, React+Vite client)
- [ ] Shared message types (pydantic models, TypeScript types)
- [ ] FSM engine: `NODE_REGISTRY`, transitions, `FieldValue` metadata
- [ ] Guardrail engine: chunk + classify utterances against defined categories
- [ ] Text-only console loop (FastAPI WebSocket + stdin)
- [ ] Session persistence (Redis active state, Postgres transcripts/summaries)
- [ ] Structured output generation (pre-visit summary)
- [x] Documentation scaffolded (README, plan, decisions, agents, dotfiles)

### Phase 1 — Voice Layer (Days 4–6)

- [ ] Deepgram WebSocket integration (streaming STT)
- [ ] ElevenLabs TTS (full-audio response, streaming later)
- [ ] Browser `MediaRecorder` capturing WebM/Opus chunks
- [ ] Voice frontend replacing text console
- [ ] Voice activity detection (VAD) and turn management

### Phase 2 — Hardening (Days 7–10)

- [ ] RAG over intake templates, symptom red flags, clinic policy (pgvector)
- [ ] LangSmith observability
- [ ] Text-only patient simulator for evals
- [ ] Error handling, reconnection, graceful degradation
- [ ] Security review (PII, PHI, auth)

### Out of Scope (permanent)

- Drug interaction advice
- Diagnosis support or ICD-10 coding
- Treatment recommendations
- Full EHR integration

## Key Design Decisions

See [DECISIONS.md](DECISIONS.md) for rationale behind FSM vs. graph, guardrail architecture, and other trade-offs.
