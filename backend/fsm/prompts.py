PROMPTS: dict[str, str] = {
    "greeting": (
        "Hello, welcome to VoiceIntake. I'll be collecting some information "
        "before your visit. Please tell me your full name and date of birth."
    ),
    "identity": ("Thank you. Could you please provide or confirm your date of birth?"),
    "chief_complaint": ("What brings you in today? Please describe your main concern."),
    "symptoms": (
        "Can you tell me more about your symptoms? When did they start, and how severe are they?"
    ),
    "history": (
        "Do you have any significant medical history or ongoing conditions that I should note?"
    ),
    "allergies": ("Do you have any allergies to medications, foods, or anything else?"),
    "medications": (
        "Are you currently taking any medications, including over-the-counter or supplements?"
    ),
    "visit_reason": ("Is there anything else that prompted you to schedule this visit today?"),
    "confirmation": (
        "Thank you. I'd like to review what I've gathered before we finish. "
        "Does everything look correct?"
    ),
    "handoff": (
        "I'm having trouble processing your responses. Let me connect you "
        "with a team member who can assist further."
    ),
}
