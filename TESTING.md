# Testing

This repo uses lightweight smoke checks for backend regressions and TypeScript
build checks for the frontend. The frontend does not currently include a browser
test runner, so WebSocket-only browser behavior is verified manually.

## Backend Regression Smoke Checks

Run these from the repo root:

```bash
PYTHONPATH=. uv run python -m backend.tests.smoke_summary_persistence_order
PYTHONPATH=. uv run python -m backend.tests.smoke_rag_unavailable
PYTHONPATH=. uv run python -m backend.tests.smoke_retry_handoff
```

Coverage:

- `smoke_summary_persistence_order` monkeypatches RAG enrichment to add
  `clinician_context`, completes REST and WebSocket sessions, and verifies
  `repo.save_summary` receives the enriched summary.
- `smoke_rag_unavailable` monkeypatches DB session creation and context entry
  failures, then verifies `enrich_summary_with_rag` does not raise and marks
  `clinician_context.rag_status` as `unavailable`.
- `smoke_retry_handoff` simulates max retries on the identity node and verifies
  the final retry immediately returns `call_complete=true` and
  `handoff_triggered=true`.

## Frontend Manual Regression: WebSocket Text Mode

Use this check after changes to `frontend/src/App.tsx` or
`frontend/src/useIntakeSocket.ts`.

1. Start the backend:

   ```bash
   PYTHONPATH=. uv run uvicorn backend.main:app --reload
   ```

2. Start the frontend:

   ```bash
   cd frontend
   npm run dev
   ```

3. Open the app in a browser and open DevTools.
4. In the Network tab, watch both Fetch/XHR requests and WebSocket frames.
5. Select WebSocket text mode in the UI.
6. Refresh the page or start with no existing connected intake socket.
7. Type a first message, such as `Alex Rivera`, and click Send.
8. Expected result:
   - The frontend opens the intake WebSocket.
   - The message is sent as a WebSocket text frame only after the socket is open.
   - No `/text/intake/{session_id}` REST request is made for that message.
   - The user message appears once in the transcript.
9. Stop the backend or block the WebSocket connection, then send another message
   while still in WebSocket mode.
10. Expected failure result:
    - The app shows an explicit WebSocket connection error.
    - The message is not silently sent through REST.
    - Loading state clears and the voice orb returns to idle.
11. Switch to REST text mode and send a message.
12. Expected REST result:
    - The message is sent through `/text/intake/{session_id}`.
    - REST mode behavior is unchanged.
13. Start voice intake once after the text-mode check.
14. Expected voice result:
    - Voice startup still opens the WebSocket and sends `voice_start`.
    - Microphone capture and voice flow are unchanged.

