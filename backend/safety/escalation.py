"""
Red-flag escalation — deterministic keyword matching against a local JSON
knowledge base of symptom red flags.

Called after extraction on every user turn.  If a CRITICAL flag is matched
the intake is immediately routed to handoff.  HIGH flags are recorded in
the session state but do not interrupt the flow.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_KB_BASE = Path(__file__).resolve().parent.parent.parent
_KB_PATH = _KB_BASE / "knowledge_base" / "symptom_redflags" / "redflags.json"


@dataclass
class EscalationResult:
    triggered: bool
    flag_id: Optional[str] = None
    label: Optional[str] = None
    severity: Optional[str] = None
    immediate_handoff: bool = False
    description: Optional[str] = None


def _load_flags() -> list[dict]:
    """Load the red-flag knowledge base from disk.

    Returns an empty list if the file is missing (no escalation possible).
    """
    try:
        with open(_KB_PATH) as f:
            data = json.load(f)
        return data.get("flags", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


_FLAGS: list[tuple[re.Pattern, dict]] = []


def _init_patterns() -> None:
    global _FLAGS
    if _FLAGS:
        return
    for flag in _load_flags():
        keywords = flag.get("keywords", [])
        if not keywords:
            continue
        pattern = re.compile(
            "|".join(re.escape(kw) for kw in keywords),
            re.IGNORECASE,
        )
        _FLAGS.append((pattern, flag))


def check_escalation(user_utterance: str) -> Optional[EscalationResult]:
    """Check *user_utterance* against the red-flag knowledge base.

    Returns an ``EscalationResult`` when a match is found, or ``None``
    when no red flag is triggered.
    """
    if not user_utterance.strip():
        return None
    _init_patterns()
    for pattern, flag in _FLAGS:
        if pattern.search(user_utterance):
            return EscalationResult(
                triggered=True,
                flag_id=flag.get("id"),
                label=flag.get("label"),
                severity=flag.get("severity"),
                immediate_handoff=flag.get("immediate_handoff", False),
                description=flag.get("description"),
            )
    return None
