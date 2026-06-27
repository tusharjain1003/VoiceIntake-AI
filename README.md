# VoiceIntake AI

A real-time clinical intake voice assistant that collects patient intake information via browser-based voice or text, navigates a structured finite state machine, and generates a pre-visit summary for clinician review. Built with a **safety-first** design — it never diagnoses, treats, or interprets medical data.

## Safety Boundary

VoiceIntake AI **does not**:
- Diagnose, prescribe, or recommend treatment
- Interpret test results or provide medical advice
- Perform ICD-10 coding, drug interaction checks, or EHR integration

It **only** collects and structures information. The system can trigger a human handoff at any point when red flags are detected (chest pain, suicidal ideation, etc.).

## Architecture

```
Browser (React + TS)
  │
  ├── WebSocket ──► FastAPI ──► FSM ──► LLM (GPT-4o-mini)
  │   (audio)       │            │          │
  │                  │            ├── Guardrail layer
  │                  │            ├── Escalation engine
  │                  │            └── Field extraction
  │                  │
  ├── REST ────────► FastAPI ──► TTS (ElevenLabs)
  │   (text)         │
  │                  ├── STT (Deepgram)
  │                  ├── Redis (active sessions)
  │                  └── Postgres (durable storage)
  │
  └── Evals (pytest) ──► Patient simulator ──► FSM ──► Metrics
      (text-only offline)
```

**Two modes of operation:**
1. **Voice mode** — WebSocket with streaming audio (WebM/Opus), Deepgram STT, ElevenLabs TTS.
2. **Text-only mode** — REST endpoint, no audio dependencies.

The core FSM logic, guardrails, and field extraction are **modality-agnostic** — the same engine powers both modes.

## Local Setup

### Prerequisites
- Python 3.12+ with `uv`
- Node.js 20+
- Docker (Postgres + Redis)
- API keys for GPT-4o-mini (OpenAI), Deepgram, ElevenLabs, LangSmith (optional)

### 1. Clone and install

```bash
git clone <repo>
cd voiceintake-ai

# Backend
uv sync

# Frontend
cd frontend && npm install && cd ..
```

### 2. Environment variables

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | GPT-4o-mini access |
| `DEEPGRAM_API_KEY` | Voice only | Streaming STT |
| `ELEVENLABS_API_KEY` | Voice only | TTS |
| `DATABASE_URL` | Yes | Postgres DSN (default: `postgresql+psycopg://postgres:postgres@localhost:5432/voiceintake`) |
| `REDIS_URL` | Yes | Redis DSN (default: `redis://localhost:6379`) |
| `LANGCHAIN_API_KEY` | Tracing | LangSmith tracing |
| `LANGCHAIN_PROJECT` | No | LangSmith project name (default: `voiceintake-ai`) |
| `DEV_MODE` | No | Set `true` to use in-memory session store when Redis is unavailable (for local dev without Docker) |

### 3. Start infrastructure

```bash
docker-compose up -d
```

### 4. Run database migrations

The app auto-creates tables on startup (`SQLAlchemy` metadata create_all). For production, use Alembic.

### 5. Start the backend

```bash
PYTHONPATH=. uv run uvicorn backend.main:app --reload
```

### 6. Start the frontend

```bash
cd frontend && npm run dev
```

Open http://localhost:5173

## How to Run Text Mode

**Via the UI:** Just type in the text input below the voice orb and press Send. No microphone needed.

**Via REST API:**
```bash
curl -X POST http://localhost:8000/text/intake/new \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi, my name is Sam"}' | jq
```

Each response returns `assistant_message`, `current_node`, `extracted_fields`, and `call_complete`. Follow the conversation by replacing `new` with the returned `session_id`:

```bash
# Start
curl -s -X POST http://localhost:8000/text/intake/new \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi, my name is Sam"}' | jq '.session_id' -r
# → abc123

# Continue
curl -s -X POST http://localhost:8000/text/intake/abc123 \
  -H "Content-Type: application/json" \
  -d '{"message": "I was born on 05/15/1980"}'
```

## How to Run Voice Mode

1. Open http://localhost:5173
2. Click the microphone orb (turns blue/purple when idle)
3. Speak naturally — the FSM will guide the conversation
4. The orb animates: green (listening) → yellow (processing) → purple (speaking)
5. Red orb + banner = safety handoff triggered

**Troubleshooting:** If voice doesn't work, check browser microphone permissions and ensure Deepgram/ElevenLabs keys are set. Use text mode as fallback.

## How to Run Evals

The eval harness simulates patients end-to-end through the FSM (text only):

```bash
PYTHONPATH=. uv run python -m backend.evals.run_evals --runs 50
```

This runs 11 patient scenarios × 50 repetitions each:
- Standard checkup, chest pain (red flag), suicidal ideation, elderly with multiple conditions, many medications, parent calling for child, patient corrections, vague patient, and more.

Output:
- **Console** — aggregate table with completion rate, field accuracy, escalation precision/recall, latency
- **`backend/evals/EVAL_REPORT.md`** — markdown report
- **`backend/evals/eval_results.json`** — raw per-scenario-run results

Flags:
- `--runs N` — runs per scenario (default: 50)
- `--output-dir PATH` — output directory (default: `backend/evals/`)

## Screenshots

<!-- TODO: Add screenshots -->
- ![Three-panel UI](docs/screenshots/ui-overview.png) — Left: extracted fields, Center: transcript, Right: voice controls + latency
- ![Handoff banner](docs/screenshots/handoff.png) — Red flag escalation triggered
- ![Summary view](docs/screenshots/summary.png) — Final pre-visit summary

## Demo Script

A 2-minute walkthrough:

1. **Open the app** at http://localhost:5173
2. **Start text mode** — type "Hi, my name is Sam Wilson" and press Send
3. **Follow the FSM** — the assistant asks for DOB, chief complaint, symptoms, history, allergies, medications, visit reason
4. **Observe field extraction** — the left panel populates in real time with confidence scores
5. **Complete the intake** — the assistant reads back the summary, user confirms
6. **View the summary** — the left panel shows the final structured pre-visit summary
7. **Reset** — click "Reset Session" to start over

For voice mode: click the mic orb and speak responses naturally. For red flag demo: answer "chest pain" when asked about the chief complaint.

## License

Proprietary — see LICENSE.
