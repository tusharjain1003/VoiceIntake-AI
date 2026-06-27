import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class TurnLatency:
    turn_id: str
    turn_number: int
    timestamp: float  # unix seconds
    stt_final_ms: Optional[float] = None
    fsm_ms: Optional[float] = None
    tts_ms: Optional[float] = None
    total_response_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "turn_number": self.turn_number,
            "timestamp": self.timestamp,
            "stt_final_ms": self.stt_final_ms,
            "fsm_ms": self.fsm_ms,
            "tts_ms": self.tts_ms,
            "total_response_ms": self.total_response_ms,
        }


class TurnTiming:
    """Mutable holder for per-turn timing marks."""

    def __init__(self) -> None:
        self.reset_utterance()
        self.turn_counter: int = 0
        self.turn_id: str = ""
        self.stt_final_time: float = 0.0
        self.fsm_start: float = 0.0
        self.fsm_end: float = 0.0
        self.tts_start: float = 0.0
        self.tts_end: float = 0.0

    def reset_utterance(self) -> None:
        self.utterance_chunk_time: float = 0.0

    def start_turn(self) -> None:
        self.turn_counter += 1
        self.turn_id = str(uuid.uuid4())
        self.stt_final_time = 0.0
        self.fsm_start = 0.0
        self.fsm_end = 0.0
        self.tts_start = 0.0
        self.tts_end = 0.0

    def snapshot(self) -> TurnLatency:
        now = time.time()
        stt_ms = (
            (self.stt_final_time - self.utterance_chunk_time) * 1000
            if self.utterance_chunk_time > 0 and self.stt_final_time > 0
            else None
        )
        fsm_ms = (
            (self.fsm_end - self.fsm_start) * 1000
            if self.fsm_start > 0 and self.fsm_end > 0
            else None
        )
        tts_ms = (
            (self.tts_end - self.tts_start) * 1000
            if self.tts_start > 0 and self.tts_end > 0
            else None
        )
        total_ms = (
            (self.tts_end - self.stt_final_time) * 1000
            if self.stt_final_time > 0 and self.tts_end > 0
            else None
        )

        return TurnLatency(
            turn_id=self.turn_id,
            turn_number=self.turn_counter,
            timestamp=now,
            stt_final_ms=round(stt_ms, 1) if stt_ms is not None else None,
            fsm_ms=round(fsm_ms, 1) if fsm_ms is not None else None,
            tts_ms=round(tts_ms, 1) if tts_ms is not None else None,
            total_response_ms=round(total_ms, 1) if total_ms is not None else None,
        )

    def set_first_chunk(self, mono_time: float) -> None:
        if self.utterance_chunk_time == 0.0:
            self.utterance_chunk_time = mono_time

    def to_client_dict(self) -> dict:
        snap = self.snapshot()
        return {
            "turn_id": snap.turn_id,
            "metrics": {
                "stt_final_ms": snap.stt_final_ms,
                "fsm_ms": snap.fsm_ms,
                "tts_ms": snap.tts_ms,
                "total_response_ms": snap.total_response_ms,
                "timestamp": snap.timestamp,
            },
        }
