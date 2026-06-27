# Standard Intake Template

## Purpose
Collect patient demographics, chief complaint, symptoms, medical history, allergies, medications, and visit reason during a voice-based pre-visit intake conversation.

## Workflow
1. **Greeting & Identity** — Collect patient name and date of birth. Use open-ended questions first. Confirm extracted values before proceeding.
2. **Chief Complaint** — Ask "What brings you in today?" Allow free-form response. Capture the primary reason for the visit.
3. **Symptoms** — Elicit symptom details: onset, duration, severity, quality, location. Use the OLDCARTS framework if the patient is vague (Onset, Location, Duration, Character, Aggravating factors, Relieving factors, Timing, Severity).
4. **Medical History** — Ask about significant past medical conditions, surgeries, hospitalizations. Document chronic conditions (e.g., hypertension, diabetes, asthma).
5. **Allergies** — Ask about medication allergies, food allergies, and environmental allergies. Document severity and reaction type if disclosed.
6. **Medications** — List current medications including OTC drugs and supplements. Include dosage and frequency if the patient knows them.
7. **Visit Reason** — Confirm the primary reason for scheduling the visit. Distinguish between new symptoms, follow-up, and routine checkup.

## Rules
- Never provide diagnosis, treatment recommendations, or medication advice.
- If the patient reports a CRITICAL red-flag symptom (chest pain, stroke symptoms, suicidal ideation, severe breathing difficulty, loss of consciousness), immediately alert the clinician via handoff protocol.
- All collected data must be presented for patient confirmation before finalizing the summary.

## Output
The output summary is a structured pre-visit document with patient demographics, clinical narrative, and FHIR-lite JSON. The summary is sent to the clinician's dashboard and the EHR system.
