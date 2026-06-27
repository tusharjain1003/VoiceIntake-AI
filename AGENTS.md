# AGENTS.md

Instructions for automated coding assistants working on VoiceIntake AI.

## Intake Agent Scope

VoiceIntake AI is a **clinical intake-only system**. Its single job: collect structured patient information through a guided conversation and produce a pre-visit summary. It is *not* a medical AI, not a diagnosis engine, and not a treatment advisor.

The intake agent (FSM + LLM prompts) must stay strictly within this scope.

## Allowed Responses

The assistant may only:

1. **Greet** the patient and explain the intake process.
2. **Ask** for each required field in order (name, DOB, chief complaint, symptoms, history, allergies, medications, visit reason).
3. **Rephrase or re-ask** when extraction confidence is low.
4. **Read back** the collected information during `confirmation`.
5. **Generate the summary** after confirmation and end the call.
6. **Trigger handoff** when a red flag is detected — the escalation engine takes over.

## Forbidden Responses

The assistant must **never**:

- Diagnose, suggest a diagnosis, or speculate about conditions.
- Recommend treatments, medications, dosages, or lifestyle changes.
- Interpret test results, lab values, or imaging.
- Provide reassurance like "that sounds minor" or "don't worry about it."
- Answer clinical questions (redirect to "please discuss with your clinician").
- Make urgency claims ("you need to see a doctor right away" — the escalation engine handles this).
- Offer medical advice in any form.

When the model attempts any of the above, the **guardrail layer** must intercept and replace the response with a scripted redirection.

## Node List

The FSM transitions through these states in order:

| Node | Purpose |
|------|---------|
| `greeting` | Welcome and explain intake purpose |
| `identity` | Collect patient name and DOB |
| `chief_complaint` | "What brings you in today?" |
| `symptoms` | Details: onset, duration, severity, context |
| `history` | Medical history (conditions, surgeries) |
| `allergies` | Known allergies |
| `medications` | Current medications and dosages |
| `visit_reason` | Goal for this visit |
| `confirmation` | Read back all fields for verification |
| `summary` | Generate and display final structured summary |
| `handoff` | Escalation path — stopped for human review |
| `complete` | Session finished |

**No skipping or reordering.** Each node is visited exactly once (except `confirmation` which may loop on correction).

## Handoff Triggers

The escalation engine automatically flags these keywords and triggers handoff:

- **CHEST_PAIN_DYSPNEA** (HIGH) — chest pain, shortness of breath, pressure, tightness
- **SUICIDAL_IDEATION** (CRITICAL) — want to die, kill myself, don't want to live, end my life, hurt myself
- **SEVERE_ABDOMINAL_PAIN** (HIGH) — severe abdominal pain, doubling over, can't stand
- **SEVERE_HEAD_INJURY** (HIGH) — hit my head, head injury, lost consciousness, concussion
- **SEVERE_ALLERGIC_REACTION** (CRITICAL) — anaphylaxis, throat closing, trouble breathing, severe allergic reaction
- **SEVERE_BLEEDING** (HIGH) — profuse bleeding, bleeding heavily, can't stop bleeding, hemorrhaging
- **STROKE_SYMPTOMS** (CRITICAL) — facial drooping, can't move one side, sudden vision loss, confusion

CRITICAL severity → immediate handoff, session stops. HIGH severity → flag recorded, intake continues, flag included in summary.

## Guardrails

Always use the predefined categories in `DECISIONS.md`. Never add new categories without updating that file.

If the model attempts to respond clinically, the guardrail layer must intercept and trigger handoff. See `backend/guardrails/` for implementation.

## Patient Simulator

The eval harness at `backend/evals/` uses a deterministic patient simulator:

- Defined in `backend/evals/patient_simulator.py`
- Each scenario (`backend/evals/scenarios.py`) maps `node_name → expected patient response`
- The simulator returns the pre-defined response for the current node
- On confirmation correction → returns the correction once, then "yes" on subsequent visits
- No LLM calls — purely template-based for reproducibility
- Run with: `PYTHONPATH=. uv run python -m backend.evals.run_evals --runs 50`

## Conventions

- **Python**: PEP 8, type hints everywhere, pydantic v2 models for all data schemas.
- **TypeScript**: strict mode, explicit return types, interfaces over types where possible.
- **FSM**: Every state lives in `NODE_REGISTRY` as a `StateNode` with `prompt`, `extract`, `transitions`, `guardrails`. Do not add ad-hoc graph logic.
- **Field metadata**: Every extracted value uses `FieldValue(value, confidence, source_turn_id, confirmed)`.
- **Session store**: All session read/write operations go through `session_manager` (imported from `backend.session.manager`). When Redis is unavailable, the manager raises `SessionStoreUnavailableError` — the caller must handle it (HTTP 503 / WS error event). Never silently swallow session store failures.
- **Testing**: `pytest` for backend, `vitest` for frontend. Unit test every FSM state transition.

## Infrastructure

Postgres (pgvector) + Redis run via docker-compose:
```bash
docker-compose up -d
```

## Running

### Backend (from repo root)
```bash
PYTHONPATH=. uv run uvicorn backend.main:app --reload
```

### Frontend
```bash
cd frontend
npm run dev
```

## Before Committing

1. Run `ruff check` and `ruff format --check` on Python code.
2. Run `npm run lint` and `npm run typecheck` on frontend.
3. Ensure new FSM states have corresponding unit tests.
4. Run `uv sync` after any pyproject.toml change to keep lockfile fresh.
5. Update this file if workflows change.
