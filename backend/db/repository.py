"""
Postgres persistence for durable audit logging of clinical intake data.

Keeps Redis as the live session store; Postgres holds historical/audit rows
for each turn (session snapshots, transcripts, safety events, escalations,
latency events, and final summaries).

All methods are best-effort — failures log a warning but never block the
user flow.  Summary writes log errors visibly since losing the final
summary is a data-loss event.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    EscalationEventRow,
    LatencyEventRow,
    SafetyEventRow,
    SessionRow,
    SummaryRow,
    TranscriptRow,
)
from backend.session.models import SessionData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — set once at startup
# ---------------------------------------------------------------------------
_session_factory: Any = None  # async_sessionmaker or None


def init_repository(session_factory: Any) -> None:
    global _session_factory
    _session_factory = session_factory


def is_available() -> bool:
    return _session_factory is not None


async def ping() -> bool:
    """Lightweight connectivity check — returns True if DB responds."""
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _maybe_warn(desc: str, exc: Exception) -> None:
    logger.warning("Postgres persistence skipped — %s: %s", desc, exc)


# ---------------------------------------------------------------------------
# Session row — upserted on every turn
# ---------------------------------------------------------------------------


async def save_session(data: SessionData) -> bool:
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            row = await _get_session_row(db, data.session_id)
            now = _now()
            if row is None:
                row = SessionRow(session_id=data.session_id, created_at=now)
                db.add(row)
            row.current_node = data.current_node.value
            row.extracted_fields = (
                data.extracted_fields.model_dump() if data.extracted_fields else {}
            )
            row.call_complete = data.call_complete
            row.turn_count = data.turn_count
            row.retry_count_by_node = data.retry_count_by_node or {}
            row.handoff_triggered = data.handoff_triggered
            row.red_flag_severity = data.red_flag_severity
            row.red_flag_id = data.red_flag_id
            row.handoff_reason = data.handoff_reason
            row.updated_at = now
            await db.commit()
        return True
    except Exception as exc:
        _maybe_warn("save_session", exc)
        return False


async def _get_session_row(db: AsyncSession, session_id: str) -> Optional[SessionRow]:
    result = await db.execute(select(SessionRow).where(SessionRow.session_id == session_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Transcript rows — inserted on every turn (user + assistant)
# ---------------------------------------------------------------------------


async def save_transcript(session_id: str, turn_number: int, role: str, text: str) -> bool:
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            db.add(
                TranscriptRow(
                    session_id=session_id,
                    turn_number=turn_number,
                    role=role,
                    text=text,
                )
            )
            await db.commit()
        return True
    except Exception as exc:
        _maybe_warn("save_transcript", exc)
        return False


# ---------------------------------------------------------------------------
# Summary row — upserted once at session completion
# ---------------------------------------------------------------------------


async def save_summary(session_id: str, summary_data: dict) -> bool:
    if _session_factory is None:
        logger.error("Cannot persist summary — Postgres unavailable")
        return False
    try:
        async with _session_factory() as db:
            result = await db.execute(select(SummaryRow).where(SummaryRow.session_id == session_id))
            row = result.scalar_one_or_none()
            if row is None:
                row = SummaryRow(session_id=session_id)
                db.add(row)
            row.summary_data = summary_data
            await db.commit()
        return True
    except Exception as exc:
        logger.error("Failed to persist summary — data may be lost: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Latency event — inserted per turn when available (WS path only)
# ---------------------------------------------------------------------------


async def save_latency_event(session_id: str, turn_number: int, metrics: dict[str, Any]) -> bool:
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            db.add(
                LatencyEventRow(
                    session_id=session_id,
                    turn_number=turn_number,
                    stt_final_ms=metrics.get("stt_final_ms"),
                    fsm_ms=metrics.get("fsm_ms"),
                    tts_ms=metrics.get("tts_ms"),
                    total_response_ms=metrics.get("total_response_ms"),
                )
            )
            await db.commit()
        return True
    except Exception as exc:
        _maybe_warn("save_latency_event", exc)
        return False


# ---------------------------------------------------------------------------
# Safety event — inserted when the guardrail layer fires
# ---------------------------------------------------------------------------


async def save_safety_event(
    session_id: str,
    turn_number: int,
    category: str,
    original_text: str,
    replacement_text: Optional[str] = None,
) -> bool:
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            db.add(
                SafetyEventRow(
                    session_id=session_id,
                    turn_number=turn_number,
                    category=category,
                    original_text=original_text,
                    replacement_text=replacement_text,
                )
            )
            await db.commit()
        return True
    except Exception as exc:
        _maybe_warn("save_safety_event", exc)
        return False


# ---------------------------------------------------------------------------
# Escalation event — inserted when a red-flag rule is triggered
# ---------------------------------------------------------------------------


async def save_escalation_event(
    session_id: str,
    turn_number: int,
    rule_id: str,
    severity: str,
    matched_keywords: Optional[list[str]] = None,
    immediate_handoff: bool = False,
) -> bool:
    if _session_factory is None:
        return False
    try:
        async with _session_factory() as db:
            db.add(
                EscalationEventRow(
                    session_id=session_id,
                    turn_number=turn_number,
                    rule_id=rule_id,
                    severity=severity,
                    matched_keywords=matched_keywords or [],
                    immediate_handoff=immediate_handoff,
                )
            )
            await db.commit()
        return True
    except Exception as exc:
        _maybe_warn("save_escalation_event", exc)
        return False
