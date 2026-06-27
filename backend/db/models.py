import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    current_node: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    call_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count_by_node: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    handoff_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    red_flag_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    red_flag_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    transcripts = relationship(
        "TranscriptRow", back_populates="session", cascade="all, delete-orphan"
    )
    latency_events = relationship(
        "LatencyEventRow", back_populates="session", cascade="all, delete-orphan"
    )
    safety_events = relationship(
        "SafetyEventRow", back_populates="session", cascade="all, delete-orphan"
    )
    escalation_events = relationship(
        "EscalationEventRow", back_populates="session", cascade="all, delete-orphan"
    )


class TranscriptRow(Base):
    __tablename__ = "transcript_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )

    session = relationship("SessionRow", back_populates="transcripts")


class SummaryRow(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), unique=True, nullable=False, index=True
    )
    summary_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )


class LatencyEventRow(Base):
    __tablename__ = "latency_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stt_final_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    fsm_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tts_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )

    session = relationship("SessionRow", back_populates="latency_events")


class SafetyEventRow(Base):
    __tablename__ = "safety_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )

    session = relationship("SessionRow", back_populates="safety_events")


class EscalationEventRow(Base):
    __tablename__ = "escalation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    matched_keywords: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    immediate_handoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )

    session = relationship("SessionRow", back_populates="escalation_events")
