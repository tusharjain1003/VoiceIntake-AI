# VoiceIntake AI

A real-time clinical intake voice assistant that collects patient intake information via browser-based voice and generates structured pre-visit summaries for clinician review.

## 🚧 Status

Early development — text-only FSM first, voice layer added after.

## Safety Boundary

VoiceIntake AI **does not**:
- Diagnose, prescribe, or recommend treatment
- Interpret test results or provide medical advice
- Perform ICD-10 coding, drug interaction checks, or EHR integration

It **only** collects and structures information. The system can trigger a human handoff at any point.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, WebSockets |
| Frontend | React + TypeScript + Vite |
| Voice | MediaRecorder (WebM/Opus) |
| STT | Deepgram (streaming) |
| TTS | ElevenLabs |
| State | Redis (active sessions), Postgres (durable) |
| RAG | pgvector *(future)* |
| Observability | LangSmith *(future)* |
| Evals | Text-only patient simulator *(future)* |

## Quick Start

*Coming once Day 1 text FSM is complete.*

## License

Proprietary — see LICENSE.
