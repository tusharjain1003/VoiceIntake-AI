# Escalation and Red-Flag Protocol

## Overview
The voice intake system monitors patient utterances for predefined red-flag keywords. When a red flag is detected, the system escalates accordingly.

## Severity Levels

### HIGH Severity
- Examples: Chest pain (non-critical mention), shortness of breath (non-critical), abdominal pain with fever
- Action: Record the flag in the session data. Continue the intake conversation normally. The flag is visible in the clinician dashboard upon review.

### CRITICAL Severity
- Examples: Suicidal ideation, stroke symptoms, severe breathing difficulty, loss of consciousness
- Action: Immediately pause the intake conversation. Display the handoff message: "I'm going to pause the intake and connect you with a human team member now. If you feel you may be in immediate danger or this is an emergency, please contact local emergency services right away."
- The session transitions to the handoff state. The clinician dashboard highlights CRITICAL flags in red.
- If after-hours, the on-call clinician is notified immediately.

## When to Hand Off
1. Three consecutive failed extraction attempts in any FSM node route to handoff.
2. Any CRITICAL severity red flag detected in patient speech.
3. Patient explicitly refuses to continue (verbal opt-out).

## Rule Management
Red-flag rules are defined in `knowledge_base/symptom_redflags/redflags.json`. Each rule specifies:
- `id`: unique identifier
- `severity`: HIGH or CRITICAL
- `keywords`: list of trigger phrases
- `immediate_handoff`: whether to hand off immediately on match
