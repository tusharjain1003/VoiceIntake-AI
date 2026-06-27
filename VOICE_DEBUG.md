# Voice Debug Guide

Use this guide to verify the live browser voice path before demos or reviews.

## Expected Startup Sequence

1. Frontend opens a WebSocket to `/ws/intake/{session_id}`.
2. User clicks Start Voice Intake.
3. Backend logs `Voice start session=...`.
4. Backend creates the Deepgram client and logs `Creating Deepgram client session=...`.
5. Browser microphone sends MediaRecorder audio chunks over the WebSocket.
6. Backend logs audio chunks received, for example `Audio chunk #1 size=...`.
7. If audio arrives before Deepgram is fully connected, chunks are queued.
8. After Deepgram connects, queued chunks are flushed and `chunks_flushed` increases.
9. As audio is sent to Deepgram, `chunks_forwarded` and `bytes_forwarded` increase.
10. When Deepgram returns interim or final text, `transcript_events` increases.
11. When speech endpointing/finalization completes, `final_transcripts` increases.
12. Backend logs `FSM before ...` and `FSM after ...` for final transcripts.
13. Backend sends `agent_text` to the frontend.
14. ElevenLabs TTS returns audio successfully.
15. Browser receives `tts_start`, binary audio, then `tts_end`, and plays the assistant voice.

## Expected `audio_debug` Counters

During a healthy live voice session:

| Counter | Expected signal |
|---|---|
| `chunks_received` | `> 0` after the microphone starts |
| `bytes_received` | `> 0` after the microphone starts |
| `chunks_forwarded` | `> 0` after Deepgram is connected |
| `bytes_forwarded` | `> 0` after Deepgram is connected |
| `transcript_events` | `> 0` after speaking |
| `final_transcripts` | `> 0` after endpointing or voice stop/finalize |

## Troubleshooting

| Symptom | Likely issue | Check |
|---|---|---|
| `chunks_received = 0` | Frontend microphone or WebSocket issue | Browser mic permission, `mic.status`, WebSocket status, browser console errors |
| `chunks_received > 0` but `chunks_forwarded = 0` | Backend/Deepgram forwarding issue | Deepgram API key, backend logs, queued/flushed counters, Deepgram connection errors |
| `chunks_forwarded > 0` but `transcript_events = 0` | Deepgram config, audio encoding, silence, or unsupported audio | Deepgram model/language settings, actual speech input, WebM/Opus support |
| `transcript_events > 0` but no field updates | FSM trigger or final transcript issue | `final_transcripts`, `FSM before/after` logs, transcript payloads |
| `agent_text` appears but no audio | ElevenLabs or browser playback issue | ElevenLabs key/voice ID, `tts_start`/`tts_end`, binary audio frame, browser autoplay/playback errors |

## Manual Verification Steps

1. Start infrastructure if needed:
   ```bash
   docker-compose up -d
   ```
2. Start the backend:
   ```bash
   PYTHONPATH=. uv run uvicorn backend.main:app --reload
   ```
3. Start the frontend:
   ```bash
   cd frontend
   npm run dev
   ```
4. Open the app in the browser.
5. Open the browser console.
6. Start voice intake.
7. Speak one clear sentence, such as: `My name is Alex Rivera`.
8. Watch backend logs for `Voice start`, `Audio chunk`, `Deepgram connected`, and `FSM before/after`.
9. Watch browser console `audio_debug` messages.
10. Confirm the transcript appears and extracted fields update.
11. Confirm assistant text appears.
12. Confirm TTS audio plays in the browser.

## Audio Format

The browser sends audio with `MediaRecorder` as WebM/Opus chunks. The app does not capture or stream raw PCM from the browser.
