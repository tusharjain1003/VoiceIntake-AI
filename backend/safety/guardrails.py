"""
Deterministic rule-based guardrail classifier for clinical safety.

Each guardrail category maps to compiled regex patterns.
The classifier avoids broad false positives by requiring clinical
trigger words alongside structural patterns.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class GuardrailResult:
    safe: bool
    category: Optional[str] = None
    reason: Optional[str] = None
    replacement: Optional[str] = None


_SAFE_REPLACEMENT = (
    "I've noted that for the care team. Could you tell me a little more about when this started?"
)

# ---------------------------------------------------------------------------
# Clinical trigger words — required to avoid false positives on common phrasing
# ---------------------------------------------------------------------------
_DIAGNOSIS_CONDITIONS = (
    r"pneumonia|diabetes|cancer(?:ous)?|tumor|malignant|benign|infection|"
    r"fracture|concussion|asthma|bronchitis|arthritis|osteoporosis|"
    r"covid|strep|flu|migraine|seizure|stroke|heart\s+attack|"
    r"kidney\s+disease|liver\s+disease|thyroid\s+(?:disease|disorder|issue)|"
    r"anemia|UTI|acid\s+reflux|IBS|Crohn|colitis|hepatitis|cirrhosis|"
    r"emphysema|COPD|Alzheimer|Parkinson|multiple\s+sclerosis|MS|"
    r"mass|lesion|nodule|cyst|polyp|clot|aneurysm|arrhythmia|"
    r"tachycardia|bradycardia|angina|ischemia|infarction|hemorrhage|"
    r"hematoma|edema|embolism|stenosis|neuropathy|retinopathy|"
    r"sepsis|meningitis|encephalitis|cellulitis|diverticulitis|"
    r"pancreatitis|cholecystitis|appendicitis|gastroenteritis|"
    r"myocarditis|endocarditis|lymphoma|leukemia|melanoma|carcinoma|"
    r"sarcoma|glioma|concussion|hernia|ulcer|rupture"
)

_TREATMENT_MEDICATIONS = (
    r"antibiotic|statin|antidepressant|painkiller|opioid|narcotic|"
    r"benzo|steroid|insulin|blood\s+(?:thinner|pressure\s+med)|"
    r"thyroid\s+med|cholesterol\s+med|diuretic|beta.?blocker|"
    r"ACE.?inhibitor|ARB|anticoagulant|anti.?inflammatory|"
    r"antihistamine|antiviral|antifungal|chemotherapy|"
    r"immunosuppressant|muscle\s+relaxant|sleeping\s+pill|"
    r"birth\s+control|hormone\s+therapy"
)

# ---------------------------------------------------------------------------
# Category patterns
# ---------------------------------------------------------------------------
_CATEGORIES: list[tuple[str, str, re.Pattern]] = [
    # DIAGNOSIS
    (
        "DIAGNOSIS",
        "Assistant provided a clinical diagnosis.",
        re.compile(
            rf"(?i)\b(?:"
            rf"you\s+(?:may\s+)?(?:have|have\s+got)\s+(?:a\s+|an\s+)?(?:case\s+of\s+)?(?:{_DIAGNOSIS_CONDITIONS})"
            rf"|diagnos(?:ed|is)\s+(?:with\s+|as\s+)?(?:{_DIAGNOSIS_CONDITIONS})"
            rf"|you(?:'r| a)re\s+suffering\s+from\s+(?:{_DIAGNOSIS_CONDITIONS})"
            rf"|this\s+(?:sounds|looks|appears)\s+like\s+(?:a\s+|an\s+)?(?:case\s+of\s+)?(?:{_DIAGNOSIS_CONDITIONS})"
            rf"|it(?:'s| is)\s+(?:a\s+|an\s+)?"  # "it's pneumonia"
            rf"(?:{_DIAGNOSIS_CONDITIONS})"
            rf")\b"
        ),
    ),
    # TREATMENT_RECOMMENDATION
    (
        "TREATMENT_RECOMMENDATION",
        "Assistant recommended a specific treatment or medication.",
        re.compile(
            rf"(?i)\b(?:"
            rf"you\s+should\s+(?:take|start|begin|try|use|prescribe)\s+"
            rf"(?:a\s+|an\s+|the\s+|your\s+)?(?:{_TREATMENT_MEDICATIONS}|medication|medicine|pill|tablet|injection|shot|"
            rf"dose|dosage|treatment|therapy|regimen|course|supplement|vitamin|herbal|remedy)"
            rf"|i\s+(?:would\s+)?(?:recommend|suggest|prescribe)\s+"
            rf"(?:(?:that\s+)?you\s+(?:start\s+)?(?:taking\s+)?)?"
            rf"(?:a\s+|an\s+|the\s+|your\s+)?(?:{_TREATMENT_MEDICATIONS}|medication|medicine|pill|tablet|treatment|therapy|"
            rf"dose|dosage|supplement|vitamin|herbal|remedy)"
            rf"|you\s+need\s+to\s+(?:take|start|begin|try|use)\s+"
            rf"(?:a\s+|an\s+|the\s+|your\s+)?(?:{_TREATMENT_MEDICATIONS}|medication|medicine|pill|tablet|treatment|therapy|"
            rf"dose|dosage|supplement|vitamin)"
            rf")\b"
        ),
    ),
    # MEDICATION_CHANGE
    (
        "MEDICATION_CHANGE",
        "Assistant advised changing or stopping a medication.",
        re.compile(
            rf"(?i)\b(?:"
            rf"you\s+should\s+(?:stop|quit|cease|discontinue|hold|pause|change|switch|swap|increase|decrease|"
            rf"reduce|raise|lower|adjust|taper|wean)\s+"
            rf"(?:your\s+|the\s+|that\s+)?(?:{_TREATMENT_MEDICATIONS}|medication|meds|medicine|"
            rf"dosage|dose|prescription|pill|tablet|injection|shot|insulin|treatment|therapy)"
            rf"|don'?t\s+take\s+(?:that|your|the|this)\s+"
            rf"(?:{_TREATMENT_MEDICATIONS}|medication|meds|medicine|pill|tablet|prescription|drug)"
            rf"|stop\s+taking\s+(?:your\s+|the\s+|that\s+)?"
            rf"(?:{_TREATMENT_MEDICATIONS}|medication|meds|medicine|pill|tablet|prescription)"
            rf")\b"
        ),
    ),
    # TEST_RESULT_INTERPRETATION
    (
        "TEST_RESULT_INTERPRETATION",
        "Assistant interpreted a test or lab result.",
        re.compile(
            r"(?i)\b(?:"
            r"your\s+(?:test|lab|laboratory|blood\s+work|urine|imaging|X-ray|Xray|CT|MRI|ultrasound|"
            r"EKG|ECG|biopsy|pathology|screening|result|results|finding|findings|report|reports|"
            r"reading|readings|blood\s+test|culture|swab|panel|scan)\s+"
            r"(?:show|shows|indicate|indicates|suggest|suggests|reveal|reveals|demonstrate|demonstrates|"
            r"mean|means|is|are|was|were)"
            r"|your\s+(?:test|lab|laboratory|blood\s+work|urine|imaging|X-ray|Xray|CT|MRI|"
            r"ultrasound|EKG|ECG|biopsy|pathology|blood\s+test|culture|swab|panel|scan)\s+"
            r"(?:result|results|finding|findings|report|reports|reading|readings)\s+"
            r"(?:show|shows|indicate|indicates|suggest|suggests|reveal|reveals|demonstrate|demonstrates|"
            r"mean|means|is|are|was|were)"
            r"|this\s+(?:test|lab|result|finding|report|study|reading|outcome)\s+"
            r"(?:means|indicates|suggests|shows|reveals|demonstrates)"
            r"|(?:your|the)\s+(?:test|lab)\s+(?:came\s+back|results\s+are\s+in)"
            r")\b"
        ),
    ),
    # URGENCY_CLAIM_TO_PATIENT
    (
        "URGENCY_CLAIM_TO_PATIENT",
        "Assistant made an urgency or reassurance claim.",
        re.compile(
            r"(?i)\b(?:"
            r"you(?:'| a)re\s+(?:fine|ok(?:ay)?|all\s+right|safe|"
            r"going\s+to\s+be\s+(?:fine|ok(?:ay)?|all\s+right))"
            r"|(?:it|this|that)(?:'| i)s\s+(?:not|nothing)\s+"
            r"(?:serious|to\s+worry\s+about|a\s+big\s+deal|"
            r"an\s+emergency|urgent|cause\s+for\s+concern|dangerous|life.?threatening)"
            r"|this\s+is\s+(?:very|extremely|quite|highly)\s+(?:serious|urgent|dangerous|concerning)"
            r"|you\s+should\s+go\s+to\s+(?:the\s+)?(?:ER|emergency\s+room|hospital|urgent\s+care)"
            r"\s+(?:right\s+now|immediately|asap|as\s+soon\s+as\s+possible)"
            r")\b"
        ),
    ),
    # REASSURANCE_OR_DISMISSAL
    (
        "REASSURANCE_OR_DISMISSAL",
        "Assistant dismissed or downplayed a patient concern.",
        re.compile(
            r"(?i)\b(?:"
            r"that(?:'| i)s\s+(?:normal|fine|ok(?:ay)?|common|"
            r"not\s+(?:a\s+)?concern|nothing\s+(?:to\s+)?worry\s+about|"
            r"not\s+(?:a\s+)?big\s+deal|not\s+serious)"
            r"|don(?:'| t)?\s+worry\s+about\s+(?:it|that|this|your)"
            r"|it(?:'| i)s\s+probably\s+"
            r"(?:nothing|fine|normal|ok(?:ay)?|not\s+(?:a\s+)?(?:big\s+)?deal)"
            r"|there(?:'| i)s\s+no\s+(?:need|reason)\s+to\s+worry"
            r")\b"
        ),
    ),
]


def check_response_safety(response_text: str) -> GuardrailResult:
    """Check whether *response_text* contains unsafe clinical content.

    Returns a ``GuardrailResult`` with ``safe=True`` if the text is fine,
    or ``safe=False`` with a category, reason, and replacement message
    if the text should be blocked.
    """
    if not response_text.strip():
        return GuardrailResult(safe=True)

    for category, reason, pattern in _CATEGORIES:
        m = pattern.search(response_text)
        if m:
            return GuardrailResult(
                safe=False,
                category=category,
                reason=reason,
                replacement=_SAFE_REPLACEMENT,
            )

    return GuardrailResult(safe=True)
