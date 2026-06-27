# Guardrail engine placeholder.
#
# Categories (see DECISIONS.md):
#   DIAGNOSIS, TREATMENT_RECOMMENDATION, MEDICATION_CHANGE,
#   TEST_RESULT_INTERPRETATION, URGENCY_CLAIM_TO_PATIENT,
#   REASSURANCE_OR_DISMISSAL
#
# Each guardrail will receive the raw transcript chunk and return
# a GuardrailResult with triggered category + confidence + suggested response.
