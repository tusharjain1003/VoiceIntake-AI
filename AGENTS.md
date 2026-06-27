# AGENTS.md

Instructions for automated coding assistants working on VoiceIntake AI.

## Conventions

- **Python**: PEP 8, type hints everywhere, pydantic v2 models for all data schemas.
- **TypeScript**: strict mode, explicit return types, interfaces over types where possible.
- **FSM**: Every state lives in `NODE_REGISTRY` as a `StateNode` with `prompt`, `extract`, `transitions`, `guardrails`. Do not add ad-hoc graph logic.
- **Field metadata**: Every extracted value uses `FieldValue(value, confidence, source_turn_id, confirmed)`.
- **Guardrails**: Always use the predefined categories in `DECISIONS.md`. Never add new categories without updating that file.
- **No diagnosis/treatment**: If the model attempts to respond clinically, the guardrail layer must intercept and trigger handoff.
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

## Before committing

1. Run `ruff check` and `ruff format --check` on Python code.
2. Run `npm run lint` and `npm run typecheck` on frontend.
3. Ensure new FSM states have corresponding unit tests.
4. Run `uv sync` after any pyproject.toml change to keep lockfile fresh.
5. Update this file if workflows change.
