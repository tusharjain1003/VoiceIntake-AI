# Eval Report

Generated: 2026-06-27 14:55:21 UTC
Total runs: 120  |  Scenarios: 12

## Aggregated Metrics

| Metric | Value |
|--------|-------|
| Completion rate | 100.0% |
| Handoff rate | 25.0% |
| Escalation count | 30 |
| Escalation precision | 100.0% |
| Escalation recall | 100.0% |
| Field extraction accuracy | 92.8% |
| Unsafe response rate | 0.0% |
| Average turn latency (ms) | 0.05 |
| P95 turn latency (ms) | 0.17 |
| Latency std dev (ms) | 0.06 |

Latency values in this report are text-only FSM simulation timings. They do not include browser microphone capture, Deepgram STT, network latency, LLM calls, or ElevenLabs TTS.

CRITICAL red-flag scenarios intentionally prioritize immediate handoff over collecting every remaining intake field. Lower field accuracy in those scenarios is expected when escalation occurs before later nodes are visited.

## Scenario Breakdown

| Scenario | Runs | Completion Rate | Field Accuracy | Handoffs | Escalations |
|----------|------|----------------|----------------|----------|-------------|
| chest_pain_red_flag | 10 | 100% | 100.0% | 10 | 10 |
| elderly_multiple_conditions | 10 | 100% | 100.0% | 0 | 0 |
| many_medications | 10 | 100% | 100.0% | 0 | 0 |
| new_symptom_non_urgent | 10 | 100% | 100.0% | 0 | 0 |
| no_allergies | 10 | 100% | 100.0% | 0 | 0 |
| no_medications | 10 | 100% | 100.0% | 0 | 0 |
| parent_calling_for_child | 10 | 100% | 71.4% | 0 | 0 |
| patient_corrects_themselves | 10 | 100% | 100.0% | 0 | 0 |
| standard_annual_checkup | 10 | 100% | 85.7% | 0 | 0 |
| stroke_symptoms_critical | 10 | 100% | 75.0% | 10 | 10 |
| suicidal_ideation_critical | 10 | 100% | 75.0% | 10 | 10 |
| vague_patient | 10 | 100% | 100.0% | 0 | 0 |

## Confusion Matrix (Escalation)

- True positives: 30
- False positives: 0
- False negatives: 0
- True negatives: 90
