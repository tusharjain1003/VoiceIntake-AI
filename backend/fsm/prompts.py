PROMPTS: dict[str, str] = {
    "greeting": (
        "Hello, welcome to VoiceIntake. I'll be collecting some information "
        "before your visit. Could you please start by telling me your full name?"
    ),
    "identity": (
        "Thank you. And could you please provide your date of birth?"
    ),
    "chief_complaint": (
        "What brings you in today? Please describe your main concern."
    ),
    "symptoms": (
        "Can you tell me more about your symptoms? When did they start, "
        "and how have they been affecting you?"
    ),
    "medical_history": (
        "Do you have any significant medical history or ongoing conditions "
        "that I should note?"
    ),
    "allergies": (
        "Do you have any allergies to medications, foods, or anything else?"
    ),
    "medications": (
        "Are you currently taking any medications, including over-the-counter "
        "or supplements?"
    ),
    "visit_reason": (
        "Is there anything else that prompted you to schedule this visit today?"
    ),
    "summary": (
        "Thank you. I'd like to review what I've gathered before we finish. "
        "Does everything sound correct so far?"
    ),
}
